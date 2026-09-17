# ADR-0006: Limitación voluntaria de auditorías de accesibilidad avanzadas

**Estado:** Aceptado.
**Fecha:** 2026-09-17.

## Contexto

Tras implementar el patrón de modales accesibles (ADR implícito en `frontend/modal-service.js`) y las verificaciones automáticas básicas (`scripts/verificar_correcciones_ux.py`), surgieron recomendaciones para:

1. Integrar **axe-core** (auditorías exhaustivas de WCAG)
2. Implementar **pruebas con lectores de pantalla** (NVDA/JAWS/VoiceOver)
3. **Monitorear métricas de accesibilidad** en producción

Estas herramientas representan el estado del arte en accesibilidad web pero conllevan costos significativos:
- axe-core requiere Node.js/npm en un proyecto Python puro
- Las pruebas con lectores de pantalla son frágiles y dependen de OS/especificaciones
- El monitoreo en producción requiere métricas específicas no triviales

El sistema actual tiene:
- Frontend mínimo (2 archivos HTML/JS)
- Usuarios limitados (probablemente internos/demo)
- Recursos de desarrollo limitados
- Verificaciones estáticas que cubren atributos ARIA, focus trap y semántica

## Decisión

**Limitar voluntariamente** el alcance de las auditorías de accesibilidad a:

1. **Mantener y extender** el patrón `ModalService` para todos los diálogos futuros
2. **Ampliar gradualmente** `verificar_correcciones_ux.py` con más verificaciones estáticas
3. **No integrar axe-core** mientras el frontend no supere 5 páginas/components distintos
4. **No implementar pruebas con lectores de pantalla** hasta tener usuarios reales con discapacidades
5. **No monitorear métricas específicas de accesibilidad** en producción en esta fase

## Consecuencias

### Positivas
- **Costo de mantenimiento reducido**: sin dependencias Node.js/npm adicionales
- **CI/CD estable**: sin tests frágiles con lectores de pantalla
- **Enfoque pragmático**: recursos concentrados en funcionalidad core
- **Crecimiento sostenible**: se puede escalar gradualmente cuando justifique el ROI

### Negativas (costo aceptado)
- **Cobertura no exhaustiva**: algunas violaciones de WCAG podrían pasar desapercibidas
- **Dependencia humana**: revisión manual necesaria para cambios de diseño complejos
- **Brecha con estándares empresariales**: no cumpliría auditorías formales de nivel enterprise

### Criterios de reactivación
Las siguientes condiciones activarían la reevaluación de esta decisión:

1. **Frontend crece** a más de 5 páginas/components distintos
2. **Usuarios con discapacidades** acceden al sistema de forma regular
3. **Requisitos contractuales** exigen auditorías formales con axe-core
4. **Equipo frontend se expande** con desarrolladores especializados en accesibilidad

## Referencias
- [ADR-0004: Consentimiento explícito versionado](0004-consentimiento-explicito-por-version.md)
- [Patrón de Modales Accesibles](../patron-modales-accesibles.md)
- [Criterios de Evaluación UX](../ux-criterios-evaluacion.md)