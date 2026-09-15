# ADR-0005: Personificación en primera persona sin aviso de IA dentro del flujo conversacional

**Estado:** Aceptado, con riesgo diferido registrado.
**Fecha:** decisión de producto confirmada el 2026-09-14.

## Contexto

El sistema responde en primera persona como "La Santísima Muerte", sin
instrucción de autoidentificarse como IA dentro de la conversación normal
(prompt actual: *"Sin notas de IA"*, ver `flow.json` y
`langchain_adapter.py`). Se evaluó modificar esto para exigir honestidad
ante una pregunta directa ("¿eres una IA?") y para enrutar mensajes de
crisis emocional a un tratamiento distinto.

## Decisión

Mantener la personificación sin cambios en esta iteración de trabajo —
instrucción explícita del responsable del proyecto. Ni el tono ni el
protocolo de crisis se tocan aquí; quedan para una fase de trabajo
dedicada, con la decisión de tono (romper personaje vs. mantenerlo) y el
contenido de derivación (líneas de ayuda) pendientes de definición
explícita del responsable, no de una decisión técnica unilateral.

## Consecuencias

- **Riesgo identificado y formalmente diferido, no ignorado:** el
  clasificador de intención/emoción ya detecta `"desesperacion"` como
  categoría posible, pero ningún enrutado la usa — un usuario en crisis
  grave recibe la misma respuesta devocional estándar que cualquier otro
  mensaje. Ver el registro de aceptación de riesgo completo en
  [docs/compliance/gobernanza-ia.md](../compliance/gobernanza-ia.md) §4,
  incluida la condición de revisión obligatoria antes de cualquier
  lanzamiento público.
- La obligación de transparencia de IA (ISO/IEC 42001) se traslada fuera
  del flujo conversacional: debe quedar establecida en un lugar que el
  usuario controle activamente (términos de uso, ficha de tienda de apps,
  onboarding) — verificación pendiente en el cliente, fuera de este
  repositorio.
- Esta ADR se reemplaza, no se edita, el día que el protocolo de crisis se
  diseñe — un ADR nuevo debe enlazar aquí y documentar qué cambió y por qué.
