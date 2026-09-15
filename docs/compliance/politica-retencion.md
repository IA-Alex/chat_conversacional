# Política de Retención y Minimización de Datos

**Referencia normativa:** ISO/IEC 27701:2019 §7.4.7, principio de
limitación del plazo de conservación (GDPR Art. 5.1.e como referencia de
buena práctica internacional).
**Estado:** Vivo.
**Última actualización:** 2026-09-14.

Este documento formaliza, con carácter de política, el comportamiento que
hoy solo vivía como configuración técnica dispersa
([.env.example](../../.env.example),
[scripts/purgar_retencion.py](../../scripts/purgar_retencion.py)).

## 1. Plazos de conservación

| Categoría de dato | Plazo | Mecanismo | Base |
|---|---|---|---|
| Contenido de mensajes y resumen de memoria | 90 días desde el último mensaje de la sesión (configurable vía `SANTISIMA_RETENCION_DIAS`) | Purga automática, `scripts/purgar_retencion.py` | Minimización — no hay finalidad legítima para conservar contenido devocional indefinidamente |
| `device_id` / `session_id` (sin contenido asociado tras la purga) | Igual que el registro asociado; no se conservan de forma aislada | Cascada con la purga anterior | — |
| Logs técnicos operativos (`infrastructure/logging_config.py`) | **No definido formalmente — pendiente** | — | Debe fijarse un plazo explícito (recomendado: 30-90 días) y confirmar que los logs no contienen contenido de mensaje en texto plano |
| Backups de base de datos (si existen) | **No definido — pendiente** | — | Un backup que sobrevive a la purga programada anula la política; debe alinearse el ciclo de retención de backups con este plazo |

## 2. Borrado a solicitud del usuario

El usuario puede purgar su propia sesión en cualquier momento vía
`POST /api/v1/sesiones/{session_id}/reiniciar`, sin necesidad de
justificar el motivo ni esperar el plazo de 90 días — esto cumple con el
derecho de supresión/cancelación de forma más ágil que el mínimo legal
típico.

## 3. Minimización por diseño ya presente

- No se recolecta nombre, email ni identificador civil salvo que el
  usuario lo escriba voluntariamente dentro de un mensaje — en cuyo caso
  ese dato hereda el mismo régimen de retención que el resto del
  contenido, no un régimen distinto.
- La identidad es por dispositivo (`device_token`), no por cuenta — un
  cambio de dispositivo no permite reconstruir el historial anterior,
  limitando naturalmente la acumulación de perfil de largo plazo.

## 4. Pendientes para cerrar esta política

1. Confirmar plazo de retención de logs técnicos y backups (§1).
2. ~~Verificar que `scripts/purgar_retencion.py` se ejecuta de forma
   programada en producción~~ — **Resuelto (2026-09-14).** Se agregó un
   timer systemd de ejemplo (`scripts/systemd/santisima-purga-retencion.{service,timer}`,
   instalación documentada en `docs/despliegue.md` §7) que dispara la
   purga diariamente con `Persistent=true`. Sigue siendo responsabilidad
   del operador instalarlo y habilitarlo en cada servidor de producción —
   este repo entrega el mecanismo, no puede verificar por sí mismo que
   esté habilitado en un servidor concreto.
3. Documentar el procedimiento de purga ante una solicitud de baja del
   servicio completo (no solo de una sesión individual), si en el futuro
   existe algún identificador de nivel más alto que `device_id`.
