# ADR-0002: Identidad por dispositivo, sin cuentas ni login

**Estado:** Aceptado.
**Fecha:** previa a esta iteración de trabajo (decisión ya presente en el código base).

## Contexto

El sistema necesita identificar a cada usuario final para atar rate
limit, propiedad de sesión y (desde [ADR-0004](0004-consentimiento-explicito-por-version.md))
consentimiento — sin pedir nombre, email o contraseña, y pensado para
Android/iOS/web público, donde una API key fija embebida en el cliente se
puede extraer descompilando el binario o inspeccionando el tráfico.

## Decisión

Cada instalación de la app se registra una sola vez
(`POST /api/v1/dispositivos`, sin autenticación) y recibe un `device_id` +
`device_token` firmado con HMAC (`infrastructure/security.py`). Todo
request posterior usa ese token. `session_id` se emite atado
criptográficamente al `device_id` que lo pidió — un cliente no puede
fabricar ni reutilizar el de otro.

API keys (`Authorization: Bearer <api_key>`) quedan reservadas
exclusivamente a endpoints de administración (`/admin/*`), nunca
distribuidas en el cliente.

## Consecuencias

- **Positivo:** no se recolecta dato civil salvo que el usuario lo escriba
  voluntariamente dentro de un mensaje — reduce la superficie de dato
  personal directo (ver [docs/compliance/RoPA.md](../compliance/RoPA.md)).
- **Positivo:** reinstalar la app o cambiar de dispositivo crea una
  identidad nueva sin vínculo con la anterior — limita naturalmente la
  acumulación de perfil de largo plazo.
- **Negativo (costo aceptado):** no hay forma de recuperar el historial si
  el usuario pierde el dispositivo o reinstala — es una consecuencia
  deliberada del diseño (menos dato retenido = menos que perder), no un
  bug, pero debe comunicarse al usuario en el aviso de privacidad.
- Un dispositivo revocado (`RegistroDispositivos.revocar`) queda
  bloqueado permanentemente — no hay mecanismo de "desbloqueo" ni de
  apelación en este backend; si se necesita, es una decisión de producto
  pendiente, no un defecto de esta ADR.
