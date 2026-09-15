# ADR-0004: Consentimiento explícito versionado antes del primer mensaje

**Estado:** Aceptado.
**Fecha:** 2026-09-14.

## Contexto

El contenido de los mensajes puede revelar creencia religiosa y estado
emocional — categoría especial de dato bajo la mayoría de marcos de
protección de datos (ver
[docs/compliance/DPIA.md](../compliance/DPIA.md) §4), que exige
consentimiento **explícito** (acto afirmativo, no un aviso disponible sin
más) y **diferenciado** (separado de cualquier aceptación general de
términos de uso) antes de procesar el dato — no después.

Se descartó dejar que el usuario mandara 1-2 mensajes reales antes de
pedir el consentimiento (propuesta de producto inicial): esos mensajes ya
se habrían enviado a DeepInfra y persistido sin base legal para esa
ventana, sin que la aceptación posterior lo sanee retroactivamente.

## Decisión

- `POST /api/v1/dispositivos/consentimiento` registra, por dispositivo,
  la versión exacta del aviso aceptada (`Settings.aviso_privacidad_version`)
  con timestamp.
- `POST /api/v1/mensajes` y `.../mensajes/stream` exigen que el dispositivo
  haya aceptado la versión **vigente** (no solo alguna versión alguna vez)
  — si el aviso cambia, el consentimiento anterior deja de ser válido y el
  backend responde `403 consentimiento_requerido`.
- El registro/saludo inicial (`POST /api/v1/dispositivos`) y la creación
  de sesión no exigen consentimiento: no procesan contenido sensible.

## Consecuencias

- **Positivo:** el backend queda auditable — se puede demostrar qué texto
  exacto aceptó cada usuario y cuándo, no solo que "algo" aceptó.
- **Positivo:** subir `SANTISIMA_AVISO_PRIVACIDAD_VERSION` fuerza
  re-consentimiento de toda la base de usuarios sin código adicional.
- **Negativo (costo aceptado):** el backend no puede, por sí solo,
  garantizar que el cliente realmente muestre el recuadro antes de dejar
  escribir — solo garantiza que, si no lo hizo, el envío falla. La
  responsabilidad de mostrar la pantalla correcta es del cliente
  (app/web), fuera de este repositorio (ver
  [docs/compliance/DPIA.md](../compliance/DPIA.md) conclusión).
- Migración de esquema (`RegistroDispositivosSQLite`) diseñada para no
  romper una base de datos ya desplegada sin las columnas de
  consentimiento (`ALTER TABLE` idempotente en el arranque).
