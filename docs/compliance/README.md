# Documentación de Cumplimiento Normativo

Índice de los artefactos de cumplimiento del backend de La Santísima
Muerte, elaborados con base en los marcos ISO/IEC/IEEE 12207,
ISO/IEC 25010, ISO/IEC 27001/27701, ISO/IEC 29134, ISO/IEC 42001 y
NIST AI RMF, adaptados a la naturaleza real del sistema: una IA
conversacional que personifica una entidad venerada y procesa contenido
devocional/emocional de categoría especial.

| Documento | Qué cubre |
|---|---|
| [DPIA.md](DPIA.md) | Evaluación de impacto en protección de datos — riesgos, base legal, conclusión de si el sistema puede lanzarse |
| [RoPA.md](RoPA.md) | Registro de actividades de tratamiento — qué dato, con qué fin, con quién se comparte |
| [politica-retencion.md](politica-retencion.md) | Plazos de conservación y minimización de datos |
| [gobernanza-ia.md](gobernanza-ia.md) | Evaluación de riesgo del sistema de IA y **registro formal de aceptación de riesgo** para el protocolo de crisis diferido |
| [soa-iso27001.md](soa-iso27001.md) | Declaración de Aplicabilidad — qué controles de seguridad del Anexo A están implementados, parciales o pendientes |

## Estado general (2026-09-14)

- **Jurisdicción:** no confirmada — todos los documentos asumen México
  como referencia por defecto dado el idioma y contexto cultural del
  proyecto; deben revalidarse en cuanto se confirme el mercado de
  lanzamiento.
- **Bloqueante para lanzamiento público** (ver detalle en cada documento):
  confirmar que el cliente (app/web) realmente usa el gate de
  consentimiento ya implementado en el backend (DPIA §4/§6) antes de
  habilitar el primer mensaje, y firma del responsable del tratamiento
  sobre el riesgo de crisis diferido (gobernanza-ia.md §4).
- **No bloqueante pero pendiente:** definición de proveedor de hosting,
  rotación de clave de cifrado, plan mínimo de continuidad.
- Ningún documento de esta carpeta modifica código, prompts o
  comportamiento en tiempo de ejecución — son registros de gobernanza
  sobre el sistema tal como existe hoy.

## Lo que falta por decisión pendiente del responsable del proyecto

El protocolo de respuesta ante crisis emocional (tono, contenido de
derivación) queda explícitamente fuera de esta iteración por instrucción
directa del responsable del proyecto — el sistema mantiene la postura
devocional sin cambios. Este README y `gobernanza-ia.md` existen
precisamente para que esa decisión quede documentada como consciente y
no como una omisión.
