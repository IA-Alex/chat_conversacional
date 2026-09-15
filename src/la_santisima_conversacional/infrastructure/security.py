"""Autenticación de la API y emisión/validación de tokens firmados.

Dos identidades distintas, con propósitos distintos:

1. **Dispositivo** (``emitir_device_token`` / ``verificar_firma_device_token``):
   la identidad de cada usuario final de la app (Android/iOS/web), emitida
   por el propio servidor vía ``POST /api/v1/dispositivos`` — sin pedir
   nombre/email/contraseña. Reemplaza un primer diseño con API keys fijas
   repartidas a mano: una API key embebida en una app pública se puede
   extraer descompilando el binario o inspeccionando el tráfico, así que
   no sirve como identidad de usuario final a partir del momento en que
   la app se distribuye públicamente.
2. **API key** (``verificar_api_key``): reservada para operaciones de
   administración (p. ej. revocar un dispositivo abusivo) — un puñado de
   claves que solo tiene el operador del backend, nunca embebidas en un
   cliente público.

Ambas terminan atando un ``session_id`` (``emitir_session_id`` /
``validar_session_id``) a quien lo pidió, con el mismo mecanismo HMAC:
antes, ``session_id`` era un string libre que el llamador podía elegir a
voluntad, así que cualquiera que adivinara o recibiera el de otra persona
podía leer y continuar su conversación —contenido devocional/emocional
sensible— sin ninguna verificación de identidad.

No se usa JWT completo porque no hace falta: no hay claims adicionales ni
expiración de sesión de conversación (el historial debe sobrevivir por
``retencion_dias``, no expirar como una sesión de login). Un HMAC firmado
sobre el identificador (api_key/device_id) cubre exactamente el requisito
con una dependencia menos.
"""

import hashlib
import hmac
import logging
import secrets
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config import Settings, get_settings

logger = logging.getLogger(__name__)

# Compartido por la auth de API key (admin) y la de device_token (usuario
# final): ambas son "Authorization: Bearer <token>", solo cambia qué se
# valida con el valor una vez extraído.
bearer_scheme = HTTPBearer(auto_error=False)

_SEPARADOR = "."


def _firmar_valor(valor: str, secreto: str) -> str:
    return hmac.new(secreto.encode("utf-8"), valor.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def _hash_identidad(valor: str) -> str:
    """Deriva un identificador corto y no reversible de ``valor`` (api_key
    o device_id) para incrustar en el session_id sin exponer el valor
    crudo en algo que viaja en cada request y puede acabar en logs."""
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()[:16]


# --- Admin: API key -----------------------------------------------------


def verificar_api_key(
    credenciales: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> str:
    """Dependency de FastAPI: exige ``Authorization: Bearer <api_key>`` de administración.

    Reservada a endpoints de operación (p. ej. revocar un dispositivo) —
    nunca a los que usa la app de un usuario final. En modo debug sin
    api_keys configuradas, acepta cualquier request y devuelve una key
    sintética fija, para poder desarrollar localmente sin credenciales.
    """
    if settings.debug and not settings.api_keys:
        return "debug-api-key"

    if credenciales is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta encabezado Authorization: Bearer <api_key>.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    api_key = credenciales.credentials
    # Comparación en tiempo constante contra cada key válida para no dar
    # pie a un ataque de timing que infiera el valor correcto carácter a
    # carácter.
    es_valida = any(hmac.compare_digest(api_key, valida) for valida in settings.api_keys)
    if not es_valida:
        logger.warning("Intento de acceso admin con API key inválida.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return api_key


# --- Usuario final: device_token ----------------------------------------


def emitir_device_token(device_id: str, settings: Settings) -> str:
    """Firma ``device_id`` para devolverlo como token al dispositivo.

    A diferencia del hash usado en ``session_id``, aquí el ``device_id``
    viaja legible dentro del token (no es un secreto: es un UUID aleatorio
    generado por el servidor, no una credencial) — así el llamador puede
    recuperarlo de su propio token sin que el servidor tenga que buscarlo
    en ninguna tabla para saber "quién firmó esto".
    """
    _exigir_secreto(settings)
    firma = _firmar_valor(device_id, settings.session_secret)  # type: ignore[arg-type]
    return f"{device_id}{_SEPARADOR}{firma}"


def verificar_firma_device_token(device_token: str, settings: Settings) -> Optional[str]:
    """Devuelve el ``device_id`` si la firma es válida; ``None`` si no.

    Solo verifica que el token fue emitido por este servidor — no consulta
    si el dispositivo fue revocado (eso requiere ``RegistroDispositivos`,
    que vive en infraestructura con estado, fuera de este módulo puro).
    """
    _exigir_secreto(settings)
    partes = device_token.split(_SEPARADOR)
    if len(partes) != 2:
        return None
    device_id, firma = partes
    firma_esperada = _firmar_valor(device_id, settings.session_secret)  # type: ignore[arg-type]
    if not hmac.compare_digest(firma, firma_esperada):
        return None
    return device_id


# --- session_id: atado a quien lo pidió (api_key admin o device_id) -----


def emitir_session_id(propietario: str, settings: Settings) -> str:
    """Genera un session_id nuevo, firmado y atado a ``propietario``
    (el device_id, o el api_key en el caso admin).

    Formato: ``<hash_propietario>.<token_aleatorio>.<firma_hmac>``. El
    hash permite validar propiedad sin volver a tener ``propietario`` a
    mano tal cual; la firma impide que un cliente fabrique un session_id
    con el hash de otro propietario.
    """
    _exigir_secreto(settings)
    hash_propietario = _hash_identidad(propietario)
    token = secrets.token_urlsafe(16)
    firma = _firmar_valor(f"{hash_propietario}{_SEPARADOR}{token}", settings.session_secret)  # type: ignore[arg-type]
    return f"{hash_propietario}{_SEPARADOR}{token}{_SEPARADOR}{firma}"


def validar_session_id(session_id: str, propietario: str, settings: Settings) -> bool:
    """Verifica que ``session_id`` fue emitido por el servidor para ``propietario``.

    Devuelve False (no lanza) ante cualquier session_id malformado o con
    firma inválida, para que el llamador decida uniformemente cómo
    responder (404) sin distinguir "no existe" de "es ilegítimo" —
    distinguirlo en la respuesta filtraría información útil para enumerar
    sesiones ajenas.
    """
    _exigir_secreto(settings)
    partes = session_id.split(_SEPARADOR)
    if len(partes) != 3:
        return False
    hash_propietario, token, firma = partes
    if hash_propietario != _hash_identidad(propietario):
        return False
    firma_esperada = _firmar_valor(f"{hash_propietario}{_SEPARADOR}{token}", settings.session_secret)  # type: ignore[arg-type]
    return hmac.compare_digest(firma, firma_esperada)


def _exigir_secreto(settings: Settings) -> None:
    if not settings.session_secret:
        if settings.debug:
            # Aleatorio por proceso (no un literal fijo): un secreto
            # hardcodeado en el código fuente es equivalente a no tener
            # secreto en absoluto si SANTISIMA_DEBUG=true llega a
            # producción por error (cualquiera con acceso al repo puede
            # forjar session_id/device_token). token_urlsafe(32) se genera
            # una sola vez por instancia de Settings (se mutan y reusan,
            # igual que antes) — se mantiene estable durante toda la vida
            # del proceso, que es lo único que hace falta para desarrollo
            # local: un `--reload` de uvicorn ya arranca un proceso nuevo y
            # pierde cualquier estado en memoria, con o sin este cambio.
            settings.session_secret = secrets.token_urlsafe(32)
            logger.warning(
                "SANTISIMA_SESSION_SECRET no configurado: usando un secreto "
                "aleatorio generado para este proceso (solo válido en modo "
                "debug). Los tokens emitidos no sobrevivirán un reinicio."
            )
            return
        raise RuntimeError("SANTISIMA_SESSION_SECRET no configurado.")
