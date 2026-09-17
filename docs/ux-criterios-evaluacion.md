# Criterios de Evaluación UX — Cliente conversacional

**Autor:** revisión de UX, arquitectura de cliente y diseño gráfico.
**Alcance:** la capa de presentación (cliente web/móvil) que consume esta API.
**Estado:** criterios normativos para el cliente, con umbrales verificables.

## 0. Advertencia de alcance (por qué este documento no es una auditoría)

[`docs/accessibility.md`](accessibility.md) ya establece el límite con
precisión: **este repositorio es un backend HTTP sin interfaz de usuario**.
No hay pantallas que auditar aquí. Por lo tanto este documento **no puede
declarar cumplimiento**; define los criterios y los umbrales con los que el
cliente —todavía inexistente— deberá evaluarse, y los ancla a lo que la API
efectivamente expone hoy.

Existe una propuesta visual en [`propuesta_index/`](../propuesta_index/)
(`Santa Muerte Chat.dc.html`) construida sobre el design system **Nocturne**
(`propuesta_index/_ds/nocturne-*/`). Esa propuesta es un **prototipo de alta
fidelidad con datos mock** (`// Demo local únicamente: no se envía a ningún
backend.`, línea 126 del `.dc.html`): define dirección estética, no
integración. Los criterios de abajo se aplican contra ella y contra el
contrato real de la API.

## 1. Contrato real que el cliente debe respetar

Antes de cualquier criterio estético, el cliente hereda restricciones duras
del backend. Ninguna decisión de diseño puede violarlas.

| Endpoint / mecanismo | Contrato verificable | Consecuencia de diseño |
|---|---|---|
| `POST /api/v1/mensajes/stream` | SSE: `data: <chunk>\n\n` por token y cierre con `event: done` + `data: {"emocion": ...}` (`http_api.py:696-717`) | El cliente **debe** escuchar el evento `done` para conocer la emoción; no puede inferirla del texto. El indicador de escritura termina en `done`, no en el último `data:`. |
| `POST /api/v1/mensajes` | Respuesta única `{respuesta, emocion}` | Camino de degradación si el stream falla: reintento sin streaming, nunca pantalla en blanco. |
| `403 consentimiento_requerido` | Gate de consentimiento por versión ([ADR-0004](adr/0004-consentimiento-explicito-por-version.md)) | El consentimiento es un **bloqueo intencional** y debe poder completarse sin mouse ([`accessibility.md`](accessibility.md) §requisitos). Si falta, se muestra el gate — no un error genérico. |
| `429` rate limit | Límite por dispositivo (`infrastructure/rate_limit.py`) | Error recuperable con reintento temporizado, nunca pérdida del texto escrito en el input. |
| `404` sesión no encontrada | Sesión de otro dispositivo se reporta como 404 (`http_api.py:662`) | Mensaje neutro; no filtrar existencia de sesiones ajenas. |
| `GET /health/ready` | 503 en modo degradado (`esta_degradado`) | Aviso de estado **no solo por color** (WCAG 1.4.1): texto + icono. |
| `POST /api/v1/sesiones/{id}/reiniciar` | 204, borra historial | Acción destructiva: confirmación explícita antes de ejecutar. |
| Respuesta en streaming | WCAG 4.1.3 live regions ([`accessibility.md`](accessibility.md)) | `aria-live` obligatorio; el texto que se actualiza en silencio es invisible para un lector de pantalla. |
| Personificación 1ª persona | [ADR-0005](adr/0005-personificacion-sin-aviso-de-ia-en-el-flujo.md) | La identidad se muestra en onboarding/términos, **fuera** del flujo. El cliente no debe añadir avisos de IA dentro del chat. |
| `_validar_o_degradar` + fallback | Si el motor falla **antes** de emitir texto, llega el texto de `FALLBACK_PROMPT_TEMPLATE` (`infrastructure/prompts.py`) con apariencia normal. Si falla **después** de emitir, el stream se corta con el aviso literal `"\n\n[La conexión se interrumpió. Por favor, intenta de nuevo.]"` (`crewai_adapter.py:240`) | El cliente **debe** reconocer ese corchete como corte, no como parte de la voz de la deidad: retirarlo del texto renderizado y convertirlo en un aviso de UI. El fallback previo a cualquier token es indistinguible por diseño: no debe haber UI que prometa "fuente verificada". |
| `emocion: "desesperacion"` | El clasificador ya puede devolver `desesperacion` en `event: done`, pero **ningún enrutado la usa** ([ADR-0005](adr/0005-personificacion-sin-aviso-de-ia-en-el-flujo.md), riesgo diferido en `docs/compliance/gobernanza-ia.md` §4) | Decisión de diseño **explícita y pendiente**: si el cliente colorea o cambia la estética según `emocion`, una respuesta a una crisis grave recibiría el mismo tratamiento que cualquier otra. No introducir semántica visual por emoción hasta que exista el protocolo de crisis |

## 2. Dimensión 1 — UX & Ergonomía

**Objetivo de coherencia:** minimizar la fatiga visual; respuestas escaneables
sin bloques de texto masivos.

### 2.1 Densidad de información

| ID | Criterio | Umbral verificable | Método de verificación |
|---|---|---|---|
| `UX-D1` | Ancho de medida de lectura | 45–75 caracteres por línea en el panel de chat (equivalente a `65ch` máx.) | Medir con `ch` en el contenedor de mensajes; el prototipo usa `max-width:88%` del panel, que en desktop se satisface pero en móvil < 768px no está acotado |
| `UX-D2` | Relación panel/imagen | El panel de conversación **nunca** cede espacio en desktop por debajo del 50% (el prototipo ya usa `width:50%` en `imagePanelStyle`/`chatPanelStyle`) | Inspección de layout en 1024/1280/1440px |
| `UX-D3` | Jerarquía tipográfica en respuestas de la deidad | Máx. 2 niveles visibles simultáneos (cuerpo + acento); la deidad usa `Crimson Pro 19px/1.55`, el usuario `Work Sans 16px/1.5` | El contraste de familia separa voces sin necesidad de burbujas ni colores saturados |
| `UX-D4` | Interlineado mínimo | ≥ 1.5 en cuerpo de mensaje (el prototipo cumple: `line-height:1.55` deidad, `1.5` usuario) | Valor CSS declarado, no aparente |
| `UX-D5` | Segmentación de respuestas largas | Párrafos > 4 líneas / > 280 caracteres se dividen en ≥ 2 bloques; un solo bloque nunca supera ~8 líneas | Inspección sobre respuestas reales de la deidad (el prompt pide "máximo 2 párrafos", no un muro de texto) |
| `UX-D6` | Anclas escaneables | Cada respuesta de la deidad abre con una unidad autónoma legible (primera línea comprensible aislada, ≤ 90 caracteres) | Test de "solo primera línea": leer solo la primera línea y verificar que comunica intención |

### 2.2 Tiempos de respuesta visual (presupuesto de latencia)

Umbrales de Nielsen/RAIL aplicados al streaming:

| ID | Criterio | Umbral | Fundamento |
|---|---|---|---|
| `UX-T1` | Eco optimista del mensaje del usuario | ≤ 100 ms desde `Enter`/click | El mensaje debe aparecer en la pantalla **antes** de cualquier ida al servidor; la latencia de red nunca se percibe como "no pasó nada" |
| `UX-T2` | Indicador de actividad de la deidad | ≤ 100 ms si no hay primer token | Cubre el tiempo muerto hasta el primer `data:` del SSE |
| `UX-T3` | Primer token visible | ≤ 1.5 s p95 | El streaming existe para esto: si el primer token tarda más, el indicador de `UX-T2` debe seguir animado y no congelado |
| `UX-T4` | Estabilidad durante el stream | Sin saltos de scroll ni reflow mientras llegan tokens; auto-scroll anclado **solo** si el usuario está en el fondo de la lista | Evitar el "tirón de scroll" que arranca al usuario de su lectura |
| `UX-T5` | Control de animación continua | La niebla periférica del prototipo (3 capas, `fogDriftA/B/C`, 9.5–12 s infinitos) debe respetar `prefers-reduced-motion` y pausarse bajo interacción de lectura | Movimiento perpetuo = coste atencional permanente; el prototipo no lo respeta hoy |

**Nota de ergonomía sobre el prototipo:** la niebla se intensifica 350 ms
(`triggerIntensify`, `setTimeout(..., 350)`) al enviar. Ese pulso es un
excelente sustituto del spinner — **pero está disparado hoy en el cliente**
(`onInputKeyDown`/`onSendClick`), no por la llegada real de la respuesta.
El criterio es que quede ligado al **primer token** (`UX-T3`), no al envío.

## 3. Dimensión 2 — Flujo Conversacional

**Objetivo:** transiciones fluidas entre la entrada del usuario y la emisión
de tokens del modelo.

### 3.1 Gestión de contexto

| ID | Criterio | Umbral verificable |
|---|---|---|
| `CV-C1` | Persistencia temporal visible | Cada mensaje muestra hora (`msg.time`), sin fecha en el turno actual; separador de fecha al cambiar de día |
| `CV-C2` | Continuidad de sesión | Al reconectar, el cliente rehidrata desde la sesión existente; nunca reinicia el historial por un error de red transitorio (el historial es del backend vía sliding window, `domain/conversacion.py`) |
| `CV-C3` | Reinicio explícito | `POST /api/v1/sesiones/{id}/reiniciar` detrás de confirmación; tras 204, la UI refleja conversación vacía y un estado de primera interacción (sin resumen previo) |
| `CV-C4` | Memoria larga invisible | El resumen persistente (`extraer_resumen_persistente`) **no** se muestra como mensaje: es contexto del sistema, no contenido de conversación |
| `CV-C5` | Contexto de error recuperable | Tras 429/red, el texto del input **no** se descarta y el reintento no duplica el mensaje del usuario |

### 3.2 Interrupciones

| ID | Criterio | Umbral verificable |
|---|---|---|
| `CV-I1` | Detener generación | Aparece un control "detener" mientras el stream está activo; al pulsarlo, el texto ya recibido **se conserva** |
| `CV-I2` | Envío durante generación | El envío queda bloqueado o encolado de forma explícita; nunca dos generaciones escribiendo en el mismo mensaje |
| `CV-I3` | Segundo plano / reconexión | Al volver de `visibilitychange`, el stream roto se reconcilia con `POST /api/v1/mensajes` (no-streaming) en lugar de dejar un mensaje truncado |
| `CV-I4` | Cancelación limpia | Cancelar no deja el indicador de escritura permanente ni un cursor parpadeando |
| `CV-I5` | Gate de consentimiento a mitad de flujo | Si el consentimiento caduca (`403` por cambio de `SANTISIMA_AVISO_PRIVACIDAD_VERSION`), el gate se presenta **encima** de la conversación preservando el historial local |

### 3.3 Estados de carga

Máquina de estados mínima que el cliente debe implementar. Cada estado tiene
una única representación visual, y ninguna es "pantalla vacía":

| Estado | Disparo | Representación | Duración esperada |
|---|---|---|---|
| `idle` | Sin actividad | Placeholder `"Habla con ella..."` | — |
| `enviando` | `UX-T1` | Mensaje del usuario ya visible + input limpio | ≤ 100 ms |
| `esperando` | Sin primer `data:` | Indicador de actividad de la deidad + niebla en pulso | hasta 1.5 s p95 |
| `streameando` | Primer `data:` | Texto apareciendo token a token, cursor estable | hasta `done` |
| `completo` | `event: done` | Cursor retirado; `emocion` aplicada a la estética | — |
| `degradado` | Fallback del motor **antes** del primer token | **Idéntico a `completo`** (ver §1: indistinguible por diseño) | — |
| `interrumpido` | Stream cortado a media respuesta (`"[La conexión se interrumpió...]"`) | Texto recibido **preservado** + aviso de UI (no el corchete literal) + acción "reintentar" | — |
| `error_recuperable` | 429 / red | Aviso textual + reintento; input preservado | — |
| `error_terminal` | 403 / 404 | Aviso textual específico + acción (consentimiento / nueva sesión) | — |

**Regla de oro:** el paso de `esperando` → `streameando` debe ser un
**reemplazo in-place del indicador por texto**, sin desplazamiento de layout.
El salto de "puntos suspensivos" a "primer token" es la transición más
visible de todo el producto.

**Nota sobre `degradado`:** el fallback del motor es indistinguible de una
respuesta normal solo cuando falla antes del primer token. Un fallo a mitad
de stream **sí** es visible (llega el aviso entre corchetes), y por eso tiene
su propio estado `interrumpido` en vez de mezclarse con `completo`.

## 4. Dimensión 3 — Simetría y Uniformidad

**Objetivo:** estructura simétrica en chat.

### 4.1 Alineación y estructura

| ID | Criterio | Umbral verificable |
|---|---|---|
| `SU-A1` | Eje de voces | La deidad siempre a la izquierda (flush-left), el usuario siempre a la derecha; **sin** espejo ni alternancia |
| `SU-A2` | Regla vertical del usuario | El prototipo usa un filete de 1px (`rgba(184,150,95,0.55)`) pegado al bloque del usuario. Debe compartir altura exacta con su bloque de texto (`align-items:stretch`) y no existir en los mensajes de la deidad — la asimetría **es** la señal de autoría |
| `SU-A3` | Simetría de márgenes | El hueco entre la imagen y el panel debe ser exactamente 0 (sin gutter decorativo); la simetría se lee en el reparto 50/50, no en un margen central |
| `SU-A4` | Ritmo vertical uniforme | `gap` constante entre mensajes (`34px` en desktop en el prototipo); el espaciado **nunca** codifica la identidad del autor |
| `SU-A5` | Marcas temporales alineadas al margen de su voz | Hora de la deidad a la izquierda bajo su texto, hora del usuario a la derecha bajo el suyo (`align-items:flex-start`/`flex-end` respectivos) |
| `SU-A6` | Simetría responsive | < 768px: apilado vertical (imagen 38vh arriba, chat debajo); ≥ 768px: 50/50. El punto de quiebre es único y declarado, no ad-hoc |

### 4.2 Tipografía

| ID | Criterio | Umbral verificable |
|---|---|---|
| `SU-T1` | Dos familias, dos roles | `Crimson Pro` (serif) = voz de la deidad, incluido el placeholder del input; `Work Sans` (sans) = voz del usuario, metadatos y UI. Ninguna familia cruza de rol |
| `SU-T2` | Escala fija | `19px` deidad / `16px` usuario / `10px` marcas temporales. Prohibido introducir tamaños intermedios por longitud de texto |
| `SU-T3` | Estilo del input | El input usa la voz de la deidad (`Crimson Pro` italic) porque el usuario le **habla a ella**; es una decisión de voz, no un descuido |
| `SU-T4` | Peso | Un solo peso por rol (`500` deidad, `400` usuario). La jerarquía se construye con tamaño y espacio, nunca con bold añadido |

### 4.3 Jerarquía visual y color

| ID | Criterio | Umbral verificable |
|---|---|---|
| `SU-J1` | Un solo acento | El acento cobre (`--cal-accent` = `#b8965f`) es **línea y marca**, nunca relleno de superficies grandes |
| `SU-J2` | Marcas temporales subordinadas | Deben alcanzar 4.5:1. Se usa el token `--cal-text-meta` (`#857e75` = **4.92:1** sobre `--cal-bg`). **Prohibido** `opacity` en el texto de la hora: `opacity:0.15` componía a `#2c2a2c` = **1.38:1** (incumplía 4.5:1 y también el 3:1 de texto grande) |
| `SU-J3` | Fondo y profundidad | Fondo `--cal-bg` `#0b0a10` + panel con `backdrop-filter:blur(var(--cal-panel-blur))` sobre `--cal-panel`; la niebla (`radial-gradient` + `blur(18px)`) existe solo en los bordes, nunca bajo el texto |
| `SU-J4` | Contraste de texto | 4.5:1 mínimo para cuerpo ([`accessibility.md`](accessibility.md)). `--cal-text-deity` = **14.55:1**; `--cal-text-user` = **13.34:1** |
| `SU-J5` | Coherencia con el design system | Todo color, tipografía, espaciado y medida sale de un token `--cal-*` declarado en `:root`. **Ningún hex, rgba, nombre de fuente o px de ritmo hardcodeado** en el marcado ni en `renderVals()` |
| `SU-J6` | Elevación | Sobre fondo oscuro: borde de 1px + oscuridad ambiental, sin sombras apiladas (regla explícita de Nocturne) |

## 5. Deuda de coherencia: estado de resolución

Los diez hallazgos detectados en la revisión de la propuesta. **Los diez están
resueltos**: 1–7 y 9–10 en el código del prototipo; 8 queda como obligación
diferida hasta que el cliente exista. La columna *Evidencia* indica dónde
verificar cada uno.

| # | Hallazgo | Criterio | Resolución aplicada | Evidencia |
|---|---|---|---|---|
| 1 | Colores hardcodeados inline (`#0b0a10`, `#e8dcc8`, `rgba(184,150,95,…)`) | `SU-J5` | Sistema de tokens `--cal-*` en `:root` (superficies, texto, acento, niebla, tipografía, medida, ritmo). Todo el marcado y `renderVals()` consumen `var(--cal-*)`. Los únicos valores crudos del archivo viven **en la declaración de los tokens** | Bloque `:root`; hex crudo fuera de `:root` = 0 |
| 2 | Dos sistemas visuales sin relación declarada: Nocturne (`#9184d9`, Inter) vs. prototipo (cobre, Crimson Pro/Work Sans) | `SU-T1`, `SU-J5` | **Decidido:** son capas distintas, no competidoras. Nocturne es un sistema genérico de presentación (deck/landing, ver su `readme.md`); el prototipo es la identidad del **producto**. Se declara el namespace `--cal-*` como fuente de verdad del chat y se documenta la separación en el propio archivo | Comentario de cabecera del `:root` |
| 3 | `triggerIntensify()` se disparaba al **enviar**, no al llegar la respuesta | `UX-T3` | El pulso se elimina de `onInputKeyDown`/`onSendClick` y se mueve a `onFirstToken()`. Verificado: tras enviar, `intensify === false`; tras el primer token, `intensify === true` | Tests A2, A3 |
| 4 | Metadatos a `opacity:0.15` | `SU-J2` | Sustituido por token pre-compuesto `--cal-text-meta`. Cálculo: `0.15` → `#2c2a2c` = **1.38:1** (falla); `0.55` → `#857e75` = **4.92:1** (pasa) | Token + test F2 |
| 5 | Sin `aria-live`, roles, `prefers-reduced-motion` ni foco visible | §1, `UX-T5` | Añadido `role="log"` + `aria-live="polite"` + `aria-relevant` al contenedor; `role="status"` + `aria-live="assertive"` para cambios de estado; `<label>` asociado al input; `aria-label` en controles; `aria-hidden` en decorativos; `:focus-visible` con `outline` cobre; `@media (prefers-reduced-motion: reduce)` detiene niebla, puntitos y cursor | Test F4 |
| 6 | Sin estado `esperando` ni control de `detener` | `CV-I1`, §3.3 | Máquina de estados con `phase` único (`idle`, `esperando`, `streameando`, `completo`, `interrumpido`, `error_recuperable`, `error_terminal`), indicador de actividad en `esperando`, botón de detener que **conserva el texto recibido**, y guard de turno que descarta chunks tardíos | Tests A, C, D, E, F8–F11 |
| 7 | `max-width:88%` / `82%` sin tope en `ch` | `UX-D1` | `max-width:min(88%, var(--cal-measure))` con `--cal-measure: 62ch`. El porcentaje acota el panel; el `ch` acota la medida real de lectura | Token + test F1 |
| 8 | [`accessibility.md`](accessibility.md) declaraba "no aplicable" | §0 | **Se mantiene diferido**: la afirmación era correcta — no hay cliente que auditar. Este documento **no** convierte el prototipo en cliente. Cuando el cliente exista, ambos documentos se actualizan juntos; el prototipo ya sirve de referencia de los requisitos | §0 de este documento |
| 9 | El prototipo no reconocía el aviso de corte como estado | §1, §3.3 | Se detecta `Component.INTERRUPT_MARKER`, se **retira del texto** (con `.trim()` y limpieza del espacio colgante del texto acumulado), se marca `msg.interrupted` + `msg.interruptedNotice` —que es lo que el template pinta— y se expone la fase `interrumpido` con reintento | Tests B1–B9, incl. el marcador real con `\n\n` |
| 10 | `event: done` transporta `emocion` pero el prototipo no la consumía | §1 | `onDone()` **almacena** `emocion` y no deriva **ninguna** estética de ella. Dar tratamiento visual diferenciado a `desesperacion` sin protocolo de crisis revisado contradice [ADR-0005](adr/0005-personificacion-sin-aviso-de-ia-en-el-flujo.md). Todas las emociones se ven igual hasta que ese protocolo exista | `onDone` + test A5 |

### Hallazgos adicionales descubiertos al implementar

No estaban en la revisión original y aparecieron al escribir el código:

| Hallazgo | Impacto | Resolución |
|---|---|---|
| El template leía `msg.interrupted` / `msg.interruptedNotice`, pero el manejador **nunca escribía esos campos** | El aviso de corte era código muerto: la rama jamás se pintaría | `_markLastDeityInterrupted()` escribe ambos campos en el último mensaje de la deidad. Tests B4, B5 |
| Los `onChunk()` de una generación cancelada podían escribir en el turno nuevo | Contaminación cruzada de texto entre turnos | Contador `_turn`/`_turnId` + guard `_isCurrentTurn()`. Tests D1, D2 |
| El marcador de corte llega como `"\n\n[La conexión se interrumpió…]"`, no como texto plano | Una comparación exacta de cadena **nunca** habría coincidido | Se busca con `includes()` y se limpia con `.trim()`. Test B7 |
| `POST /api/v1/mensajes/stream` es **POST**, no GET | `EventSource` solo hace GET y no permite la cabecera `device_id`: el cliente **no puede** usar `EventSource` | Documentado en el prototipo: consumir con `fetch()` + `ReadableStream` y parsear los frames SSE a mano |

## 6. Prioridad de implementación

Los siete pasos están **aplicados** en el prototipo. Lo que falta ya no es
diseño de interacción, es la sustitución de la simulación local por el
transporte SSE real.

| # | Paso | Criterios | Estado |
|---|---|---|---|
| 1 | Eco optimista + máquina de estados | `UX-T1`, `UX-T2`, §3.3 | ✅ `sendMessage()` pinta el mensaje del usuario y limpia el input antes de tocar la red |
| 2 | Transición `esperando` → `streameando` in-place | §3.3, regla de oro | ✅ `onFirstToken()` cambia la fase; el indicador se reemplaza por el texto sin desplazar el layout |
| 3 | `aria-live` + `prefers-reduced-motion` + foco visible | §1 | ✅ Implementado y verificado |
| 4 | Pulso de niebla ligado al primer token | `UX-T3` | ✅ Movido a `onFirstToken()` |
| 5 | Detener generación + preservación de texto | `CV-I1`, `CV-C5` | ✅ `onStopClick()` conserva lo recibido; `onRetryClick()` no pierde el input |
| 6 | Unificación de tokens y convivencia Nocturne/prototipo | §5 #1–#2 | ✅ Namespace `--cal-*` declarado; separación de capas documentada |
| 7 | Acotado de medida de lectura y contraste | `UX-D1`, `SU-J2` | ✅ `--cal-measure: 62ch`; metadatos a 4.92:1 |

### Lo que queda antes de considerar el cliente implementable

1. **Transporte SSE real.** `_simularStream()` es andamiaje de depuración y debe
   desaparecer. Requiere `fetch()` + `ReadableStream` contra
   `POST /api/v1/mensajes/stream` (no `EventSource`), con el `device_id` de
   [ADR-0002](adr/0002-identidad-por-dispositivo.md).
2. **Gate de consentimiento.** El cliente debe presentar `GET /privacidad` y el
   checkbox antes de cualquier envío; hoy el prototipo asume consentimiento
   ([ADR-0004](adr/0004-consentimiento-explicito-por-version.md)).
3. **Decisión sobre `desesperacion`.** `flow.json` la clasifica pero no la
   enruta. No es un accidente técnico: es una decisión de diseño pendiente, y
   hasta que se tome, el cliente no debe insinuarla visualmente.
4. **Auditoría WCAG real** sobre el DOM renderizado, no sobre el mock.

## 7. Cómo verificar estos criterios cuando exista el cliente

- **Contraste y medida de línea:** herramientas de auditoría sobre el DOM
  renderizado, con los tokens finales, no con los valores del mock.
- **Presupuesto de latencia:** medir con red emulada (Fast 3G y Slow 4G),
  registrando `performance.now()` en el punto de envío, en el primer `data:`
  y en `event: done`.
- **Live regions:** probar con NVDA/VoiceOver — verificar que el texto
  entrante se anuncia sin cortar la lectura en curso.
- **Estados:** forzar 429, 403, 404 y corte de red a mitad de stream;
  ninguno debe dejar la pantalla vacía ni perder el texto del input.
- **Movimiento:** con `prefers-reduced-motion: reduce` activo, la niebla debe
  quedar estática.

### Verificación automática ya disponible

La lógica de la máquina de estados es código puro (sin DOM), así que puede
extraerse del prototipo y ejecutarse en Node con un `DCLogic` simulado. Esto
valida el comportamiento sin navegador y sirve como prueba de regresión:

```bash
python3 scripts/verificar_prototipo_ux.py
```

Cubre 31 aserciones sobre: eco optimista, pulso ligado al primer token (no al
envío), streaming in-place, `emocion` almacenada sin efecto visual, corte con
el marcador real (incluido el `\n\n` que emite el motor), detención con texto
preservado, descarte de chunks tardíos, errores recuperables vs. terminales, y
los tokens de contraste y medida.

**Dos límites explícitos:**

1. `propuesta_index/` está en `.gitignore`. El script **omite** la verificación
   y sale con código 0 cuando el prototipo no está (clon limpio). Es
   intencionado: convertirlo en prueba de `pytest` la haría fallar siempre en
   CI.
2. Verifica la **lógica**, no la accesibilidad ni el aspecto visual. Ambas
   siguen pendientes hasta que el cliente real exista.

## Patrones de Implementación Disponibles

### Patrón de Modales Accesibles
El proyecto ha implementado un servicio centralizado de gestión de modales con cumplimiento WCAG 2.1 AA:

- **Servicio**: `frontend/modal-service.js`
- **Documentación**: [`patron-modales-accesibles.md`](patron-modales-accesibles.md)
- **Verificación**: Incluida en `scripts/verificar_correcciones_ux.py`
- **CI/CD**: Job `accessibility` en `/.github/workflows/ci.yml`

El patrón proporciona:
- Gestión centralizada de stack de diálogos
- Focus trap automático (WCAG 2.1.1, 2.4.3)
- Manejo de tecla Escape
- Atributos ARIA automáticos
- Z-index incremental automático
- Compatibilidad con lectores de pantalla

### Responsividad Móvil
El cliente ya incluye media queries para viewports móviles (<768px):
- Layout de una columna (flex-direction: column)
- Panel de imagen a 38vh de altura
- Ajustes de padding y márgenes
- Preservación de contraste y legibilidad

### Verificación de Regresión
Las mejoras de accesibilidad se verifican automáticamente en cada PR/push mediante:
1. Tests estáticos de atributos ARIA y estructura HTML
2. Validación de uso correcto del servicio de modales
3. Verificación de eliminación de patrones antiguos (ej. `crearFocusTrap`)

### Limitación Voluntaria de Auditorías Avanzadas
Por decisión arquitectónica documentada en [ADR-0006](../adr/0006-limitacion-voluntaria-auditorias-accesibilidad.md), el proyecto **no integra**:

1. **axe-core** para auditorías exhaustivas
2. **Pruebas con lectores de pantalla** (NVDA/JAWS/VoiceOver)
3. **Monitoreo de métricas de accesibilidad** en producción

**Justificación**: Costo desproporcionado para un frontend mínimo (2 archivos) con usuarios limitados.

**Criterios de reactivación** (documentados en ADR-0006):
- Frontend supera 5 páginas/componentes distintos
- Usuarios con discapacidades acceden regularmente
- Requisitos contractuales exigen auditorías formales
- Equipo frontend se expande con especialistas en accesibilidad

**Alternativa práctica**: Ampliación gradual de `verificar_correcciones_ux.py` con más verificaciones estáticas sin dependencias externas.


