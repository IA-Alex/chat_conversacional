# Declaración de Aplicabilidad (SoA) — ISO/IEC 27001:2022 Anexo A

**Estado:** Vivo — refleja controles técnicos ya implementados en código
más los que quedan pendientes; no es una certificación, es la base para
una eventual auditoría.
**Última actualización:** 2026-09-14.

Solo se listan los controles de Anexo A relevantes para el perfil de
riesgo de este sistema (backend conversacional con dato sensible de
categoría especial). Controles orientados a infraestructura física,
recursos humanos extensos o cadena de suministro compleja se marcan como
"No aplicable en esta fase" dado el tamaño actual del proyecto —
deberán reevaluarse si el equipo/infraestructura crecen.

| Control (Anexo A) | Aplicable | Estado | Evidencia / nota |
|---|---|---|---|
| A.5.15 Control de acceso | Sí | **Implementado** | Autenticación por `device_token` (usuario final) y API key (admin), separadas por propósito — [security.py](../../src/la_santisima_conversacional/infrastructure/security.py) |
| A.5.17 Información de autenticación | Sí | **Implementado** | Tokens firmados HMAC, `session_id` no adivinable ni reutilizable entre usuarios |
| A.8.3 Restricción de acceso a la información | Sí | **Implementado** | Endpoints `/admin/*` requieren API key nunca distribuida en el cliente |
| A.8.24 Uso de criptografía | Sí | **Implementado** | Cifrado en reposo con Fernet (`SANTISIMA_CLAVE_CIFRADO`) |
| A.8.24 (rotación de claves) | Sí | **Pendiente** | No hay procedimiento documentado de rotación de `SANTISIMA_CLAVE_CIFRADO`; una rotación hoy requeriría re-cifrar el histórico manualmente |
| A.8.16 Actividades de monitoreo | Parcial | **Parcialmente implementado** | Logging estructurado JSON ([logging_config.py](../../src/la_santisima_conversacional/infrastructure/logging_config.py)); falta definir qué eventos de seguridad específicos se alertan (ej. ráfaga de intentos fallidos de auth) |
| A.8.22 Segregación de redes | No confirmado | **Pendiente de infraestructura** | Depende del despliegue final (no definido aún — ver §Pendientes) |
| A.5.23 Seguridad de la información en el uso de servicios en la nube | Sí | **Pendiente** | Sin proveedor de hosting confirmado; falta evaluar el acuerdo de servicio del proveedor final |
| A.5.19 Seguridad en relaciones con proveedores | Sí | **Parcial** | DeepInfra como subprocesador identificado ([RoPA.md](RoPA.md)); falta revisión formal de sus términos de procesamiento de datos frente a este caso de uso |
| A.8.28 Codificación segura | Sí | **Implementado** | Validación de entrada (`MensajeCreyente`), validación de salida antes de degradar (`validar_o_usar_fallback`), linting/type-checking en CI (`.pylintrc`, `.mypy.ini`, `.pre-commit-config.yaml`) |
| A.8.25 Ciclo de vida de desarrollo seguro | Parcial | **Parcialmente implementado** | Pre-commit hooks y type checking existen; falta un proceso documentado de revisión de seguridad antes de cada release |
| A.5.29 Seguridad durante la disrupción | No | **Pendiente** | No hay plan de continuidad/recuperación ante desastre documentado |
| A.5.30 Preparación TIC para continuidad | No | **Pendiente** | Mismo punto — depende de decisión de infraestructura de producción |
| A.5.34 Privacidad y protección de datos personales | Sí | **Implementado (ver documentos dedicados)** | [DPIA.md](DPIA.md), [RoPA.md](RoPA.md), [politica-retencion.md](politica-retencion.md) |
| A.8.10 Eliminación de información | Sí | **Implementado** | Purga automática por retención + borrado a solicitud del usuario |
| A.8.15 Registro (logging) | Sí | **Implementado, requiere verificación** | Confirmar que los logs no capturan contenido de mensaje en texto plano (dato sensible en logs sería una fuga paralela al control de cifrado en BD) |

## Pendientes que bloquean cerrar esta SoA como "conforme"

1. Definir proveedor de hosting/nube y evaluar su propio cumplimiento (A.5.23).
2. Documentar procedimiento de rotación de clave de cifrado (A.8.24).
3. Confirmar ausencia de contenido sensible en texto plano en logs (A.8.15).
4. Definir plan mínimo de continuidad/recuperación (A.5.29/A.5.30) — puede
   ser proporcional al tamaño actual del proyecto, no requiere un DRP
   corporativo completo en esta fase.
5. Formalizar un proceso de revisión de seguridad pre-release (A.8.25),
   aunque sea un checklist corto dado el tamaño del equipo.
