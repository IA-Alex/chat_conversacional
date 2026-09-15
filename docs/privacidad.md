# Aviso de privacidad — La Santísima Muerte (backend conversacional)

**Versión: v1** — debe coincidir exactamente con
`SANTISIMA_AVISO_PRIVACIDAD_VERSION` (ver `config.py`). Si editas el
contenido de este documento de forma material, sube ambos valores juntos:
de lo contrario `GET /privacidad` seguirá anunciando una versión que ya no
corresponde a lo que dice este archivo, y un consentimiento previo
quedaría aceptando un texto que ya no es el vigente sin que el sistema lo
detecte (ver `_exigir_consentimiento` en `presentation/http_api.py`).

Este documento es el contenido de referencia que la ventana principal debe
mostrar (o enlazar) antes del primer mensaje del creyente, y que expone
`GET /privacidad` en forma resumida para consumo programático (el
documento completo, este archivo, se sirve en
`GET /privacidad/documento`).

## Qué datos se recogen

- El **contenido de tus mensajes** y las respuestas generadas.
- Un **resumen de memoria** de la conversación (temas, emociones,
  peticiones), generado automáticamente para dar continuidad entre
  sesiones.
- Metadatos técnicos: marca de tiempo de cada mensaje, un identificador de
  dispositivo (`device_id`) y un identificador de sesión (`session_id`),
  ambos opacos y emitidos por el servidor — no contienen ni permiten
  derivar tu identidad real.

No se recoge nombre, email, ni ningún identificador civil salvo que lo
escribas tú mismo dentro de un mensaje. No hay login: la app se registra
sola en su primer uso (`POST /api/v1/dispositivos`) y usa un token propio
del dispositivo para todo lo demás — nadie más que tú puede usar ese
token, y cambiar de dispositivo (o reinstalar la app) crea una identidad
nueva sin vínculo con la anterior.

## Por qué es un dato sensible

Los mensajes pueden reflejar creencias religiosas y estado emocional —
categorías de datos que merecen un cuidado mayor que un dato genérico.
Por eso:

- El contenido se **cifra en reposo** (ver `SANTISIMA_CLAVE_CIFRADO`) en
  la base de datos del servidor.
- Se aplica una **política de retención**: los mensajes se purgan
  automáticamente pasados `SANTISIMA_RETENCION_DIAS` días (por defecto,
  90) mediante `scripts/purgar_retencion.py`, ejecutado periódicamente.
- Puedes **borrar tu conversación en cualquier momento** con
  `POST /api/v1/sesiones/{session_id}/reiniciar` — esto elimina el
  historial y el resumen de memoria de esa sesión de forma permanente.

## Con quién se comparte

El contenido de tus mensajes se envía al proveedor del modelo de lenguaje
(DeepInfra, vía la API de LangChain/CrewAI) únicamente para generar la
respuesta. No se comparte con ningún otro tercero. Revisa la política de
retención y procesamiento de datos del proveedor del modelo para el
tratamiento que este haga en su propia infraestructura.

## Tus derechos

- **Acceso**: puedes solicitar el historial de tu sesión.
- **Borrado**: `POST /api/v1/sesiones/{session_id}/reiniciar` (ver arriba).
- **Portabilidad/limitación**: contacta al operador del servicio.

Este documento describe el comportamiento que el código implementa
(`infrastructure/repositories.py`, `infrastructure/security.py`,
`scripts/purgar_retencion.py`); si el operador del servicio configura el
backend de otra forma (p. ej. sin `SANTISIMA_CLAVE_CIFRADO`), debe
actualizar este aviso para reflejarlo con precisión — un aviso de
privacidad que no coincide con el comportamiento real es peor que no
tener aviso.
