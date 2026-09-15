# Accesibilidad

**Referencia normativa:** ISO/IEC 40500:2012 (adopción ISO de WCAG 2.0),
WCAG 2.1/2.2 (W3C, referencia vigente de facto), EN 301 549 (si aplica
por contratación pública en la UE).
**Estado del cumplimiento en este repositorio: no aplicable directamente.**

## Por qué este documento no puede ser una auditoría

Este repositorio es un **backend HTTP sin interfaz de usuario** — no
renderiza HTML, no tiene pantallas, no tiene contraste de color ni
navegación por teclado que auditar. Las normas de accesibilidad (WCAG,
ISO 40500) regulan la interfaz que un humano percibe y opera, que en este
proyecto vive en un cliente (app móvil o web) que **no existe en este
repositorio** — ver conversación de diseño previa sobre el gate de
consentimiento, donde se identificó el mismo límite.

Publicar aquí una checklist de WCAG marcada como "cumplido" sería falso:
no hay nada que evaluar. Este documento existe para que, cuando el
cliente se construya, tenga los requisitos ya definidos en vez de
descubrirlos al final.

## Requisitos que el futuro cliente debe cumplir

### Compatibilidad con lo que el backend ya expone

| Elemento del backend | Requisito de accesibilidad en el cliente |
|---|---|
| `GET /privacidad` (texto del aviso) | Debe presentarse con contraste suficiente (WCAG 1.4.3, mínimo 4.5:1) y ser navegable/leíble por lector de pantalla antes de habilitar el checkbox de consentimiento |
| El checkbox de consentimiento (ver [ADR-0004](adr/0004-consentimiento-explicito-por-version.md)) | Debe ser operable por teclado y por lector de pantalla (WCAG 2.1.1, 4.1.2) — no un `<div>` con `onClick` sin rol ARIA |
| Respuesta en streaming (`POST /api/v1/mensajes/stream`) | El cliente debe anunciar contenido nuevo a tecnología asistiva sin interrumpir la lectura en curso (WCAG 4.1.3, live regions) — un stream de texto que se actualiza en silencio es invisible para un lector de pantalla si no se implementa con `aria-live` |
| Mensajes de error (403 `consentimiento_requerido`, 429 rate limit, 404 sesión) | Deben mostrarse como texto perceptible, no solo como color/ícono (WCAG 1.4.1) |
| Personificación en primera persona ([ADR-0005](adr/0005-personificacion-sin-aviso-de-ia-en-el-flujo.md)) | Si el cliente usa audio/voz para la respuesta, debe ofrecer alternativa en texto (WCAG 1.2.1) — no asumir que todo usuario puede/quiere recibir audio |

### Requisitos generales que aplican a cualquier cliente que se construya

- Texto redimensionable hasta 200% sin pérdida de contenido (WCAG 1.4.4).
- Navegación completa por teclado, sin trampas de foco (WCAG 2.1.1, 2.1.2)
  — crítico en el paso de consentimiento, que es un bloqueo intencional:
  debe poder completarse sin mouse/touch.
- Etiquetas de formulario asociadas correctamente (el campo de mensaje,
  el checkbox de consentimiento) — WCAG 1.3.1, 4.1.2.
- Sin contenido que dependa solo de color para transmitir significado
  (ej. un estado "degradado" del sistema, ver `/health/ready`) — WCAG 1.4.1.

## Qué sí puede evaluarse desde este repositorio

Nada del backend impone una barrera de accesibilidad al cliente — los
endpoints devuelven JSON plano y texto, sin restricciones que dificulten
una implementación accesible. La responsabilidad completa recae en la
capa de presentación que se construya sobre esta API.

## Pendiente

Cuando exista el cliente, este documento debe reemplazarse (o
complementarse) por una auditoría real contra WCAG 2.1 nivel AA como
mínimo — el estándar de facto para servicios públicos y privados con
obligación de accesibilidad en la mayoría de jurisdicciones.
