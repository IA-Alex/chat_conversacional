"""Capa de presentación HTTP — el backend real que expone el servicio.

Antes de este módulo, ``APILaSantisima`` (ver ``api.py``) era una clase
Python pura: no había forma de que una ventana de chat (u otro cliente)
hablara con el servicio salvo importando el paquete desde el mismo
proceso. Este módulo es el punto 1/P0 del backend: expone
``CasoDeUsoResponderMensaje`` vía HTTP con FastAPI, y ata el resto de
correcciones (auth, rate limit, validación, salud) en el mismo lugar
donde importan: el borde de confianza con el exterior.

Identidad de quien llama (ver ``infrastructure.security`` y
``infrastructure.dispositivos`` para el detalle):
- **Dispositivo** (``device_token``): la app de cada usuario final se
  registra una vez (``POST /api/v1/dispositivos``, sin auth) y usa el
  token que recibe para todo lo demás. Pensado para Android/iOS/web
  público — no requiere login ni reparte ningún secreto embebido en el
  cliente.
- **API key** (``Authorization: Bearer <api_key>``): solo para endpoints
  de administración (``/admin/...``), nunca usada por la app.

Ejecutar en desarrollo:
    uvicorn la_santisima_conversacional.presentation.http_api:app --reload

En producción: mismo ASGI app detrás de un servidor real (uvicorn con
varios workers, o gunicorn con worker uvicorn), detrás de un proxy TLS.
"""

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Iterator, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from .. import crear_servicio
from ..config import Settings, get_settings
from ..infrastructure.dispositivos import RegistroDispositivos
from ..infrastructure.logging_config import configurar_logging
from ..infrastructure.rate_limit import LimitadorTasa, LimitadorTasaProtocolo
from ..infrastructure.security import (
    bearer_scheme,
    emitir_device_token,
    emitir_session_id,
    validar_session_id,
    verificar_api_key,
    verificar_firma_device_token,
)
from .api import APILaSantisima

logger = logging.getLogger(__name__)

# Ruta al aviso de privacidad completo (docs/privacidad.md), resuelta desde
# la ubicación del paquete (no del cwd) para que sea independiente de dónde
# se invoque uvicorn. Se sirve explícitamente vía GET /privacidad/documento
# — no se monta todo ``docs/`` como estático a propósito: esa carpeta
# también contiene documentos internos de compliance (DPIA, RoPA,
# gobernanza) que nunca deben quedar públicos.
_RUTA_AVISO_PRIVACIDAD = Path(__file__).resolve().parents[3] / "docs" / "privacidad.md"


# --- Contenedor de dependencias, ensamblado una vez al arrancar ---------


class _Estado:
    """Instancias singleton del proceso: servicio, limitador, settings.

    Se guardan en un objeto simple (no variables globales sueltas) para
    que los tests puedan sustituir ``app.state`` sin depender de imports
    de módulo con efectos secundarios.
    """

    api: APILaSantisima
    limitador: LimitadorTasaProtocolo
    limitador_registro: LimitadorTasaProtocolo
    registro_dispositivos: RegistroDispositivos
    settings: Settings


def _crear_limitador(limite: int, settings: Settings, prefijo_clave: str) -> LimitadorTasaProtocolo:
    """Instancia el backend de rate limit configurado (Redis o en memoria).

    Mismo criterio que el resto de la app (ver README "Escalar a múltiples
    instancias"): con una sola instancia del backend, el limitador en
    memoria basta; ``usar_redis_rate_limit`` lo reemplaza por uno
    compartido entre instancias. ``prefijo_clave`` evita que dos
    limitadores distintos (mensajes vs. registro de dispositivo) choquen
    claves en el mismo Redis.
    """
    if settings.usar_redis_rate_limit:
        if not settings.redis_url:
            raise RuntimeError("usar_redis_rate_limit=True requiere redis_url.")
        from ..infrastructure.rate_limit import LimitadorTasaRedis

        return LimitadorTasaRedis(
            limite,
            ventana_segundos=60.0,
            redis_url=settings.redis_url,
            prefijo_clave=prefijo_clave,
        )
    return LimitadorTasa(limite)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.validar_produccion()
    configurar_logging("DEBUG" if settings.debug else "INFO")

    if settings.debug:
        # SANTISIMA_DEBUG=true relaja de golpe tres controles (auth admin
        # sin api_keys, secreto de sesión, CORS abierto sin cors_origins) —
        # intencional para desarrollo local, catastrófico si llega a
        # producción por error. No se bloquea el arranque aquí (rompería el
        # propio flujo de desarrollo que este modo existe para habilitar),
        # pero se deja una alerta imposible de pasar por alto en cualquier
        # sistema de logs/monitoreo que vigile nivel CRITICAL.
        logger.critical(
            "ARRANCANDO EN MODO DEBUG (SANTISIMA_DEBUG=true): auth de "
            "administración deshabilitada si no hay api_keys configuradas, "
            "y CORS abierto si no hay cors_origins configurado. "
            "NUNCA debe estar activo en producción."
        )

    api = crear_servicio(
        use_langchain=settings.use_langchain,
        langchain_model=settings.modelo_chat,
        modelo_chat=settings.modelo_chat,
        modelo_resumen=settings.modelo_resumen,
        modelo_clasificador=settings.modelo_clasificador,
        ventana_mensajes=settings.ventana_mensajes,
        usar_sqlite=settings.usar_sqlite,
        sqlite_db_path=settings.sqlite_db_path,
        usar_postgres=settings.usar_postgres,
        postgres_dsn=settings.postgres_dsn,
        clave_cifrado=settings.clave_cifrado,
        retencion_dias=settings.retencion_dias,
        deepinfra_api_key=settings.deepinfra_api_key,
        deepinfra_api_base=settings.deepinfra_api_base,
    )
    app.state.api = api

    # Redis solo se activa explícitamente (ver README "Escalar a múltiples
    # instancias"): con una sola instancia del backend, el limitador en
    # memoria es correcto y no requiere tener Redis corriendo.
    app.state.limitador = _crear_limitador(settings.rate_limit_por_minuto, settings, "ratelimit")
    # Limitador independiente por IP para el registro de dispositivo (sin
    # auth: es el único endpoint que un bucle automatizado puede golpear
    # sin nunca haber pasado por la app real). Ver
    # ``Settings.rate_limit_registro_por_minuto``.
    app.state.limitador_registro = _crear_limitador(
        settings.rate_limit_registro_por_minuto, settings, "ratelimit-registro"
    )

    # En debug, registro en memoria (no ensucia disco en desarrollo local);
    # fuera de debug, SQLite: el registro de revocados debe sobrevivir un
    # reinicio del proceso, o cada reinicio "olvidaría" a quién bloqueó.
    if settings.debug:
        from ..infrastructure.dispositivos import RegistroDispositivosMemory

        app.state.registro_dispositivos = RegistroDispositivosMemory()
    else:
        from ..infrastructure.dispositivos import RegistroDispositivosSQLite

        app.state.registro_dispositivos = RegistroDispositivosSQLite(settings.dispositivos_db_path)

    app.state.settings = settings
    logger.info(
        "Backend La Santísima Muerte listo (use_langchain=%s, postgres=%s, redis_rate_limit=%s).",
        settings.use_langchain,
        settings.usar_postgres,
        settings.usar_redis_rate_limit,
    )
    yield


def crear_app() -> FastAPI:
    app = FastAPI(
        title="La Santísima Muerte — API conversacional",
        version="1.0.0",
        lifespan=_lifespan,
    )

    settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins or (["*"] if settings.debug else []),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.include_router(_router())
    return app


# --- Dependencies de request ---------------------------------------------


def _get_api(request: Request) -> APILaSantisima:
    return request.app.state.api  # type: ignore[no-any-return]


def _get_limitador(request: Request) -> LimitadorTasaProtocolo:
    return request.app.state.limitador  # type: ignore[no-any-return]


def _get_registro_dispositivos(request: Request) -> RegistroDispositivos:
    return request.app.state.registro_dispositivos  # type: ignore[no-any-return]


def _get_limitador_registro(request: Request) -> LimitadorTasaProtocolo:
    return request.app.state.limitador_registro  # type: ignore[no-any-return]


def _exigir_tasa_registro(
    request: Request,
    limitador_registro: LimitadorTasaProtocolo = Depends(_get_limitador_registro),
) -> None:
    """Rate limit por IP para ``POST /api/v1/dispositivos``.

    Sin device_id (recién no existe uno) el único identificador disponible
    es la IP de origen. Límite deliberadamente holgado (ver
    ``Settings.rate_limit_registro_por_minuto``): un usuario real registra
    su dispositivo una sola vez, así que esto nunca debería tocarle — solo
    corta un bucle automatizado generando identidades para gastar cupo del
    LLM. Si el backend corre detrás de un proxy, ``request.client.host``
    refleja la IP real solo si el proxy está configurado para reescribirla
    (p. ej. ``ProxyHeadersMiddleware`` de uvicorn); si no hay IP disponible,
    se falla abierto (no se bloquea al usuario) bajo una clave compartida.
    """
    ip = request.client.host if request.client else "ip-desconocida"
    if not limitador_registro.permitir(ip):
        logger.warning("Límite de registro de dispositivo excedido para IP %s.", ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados registros de dispositivo. Intenta de nuevo en breve.",
        )


def verificar_dispositivo(
    request: Request,
    credenciales: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
    registro: RegistroDispositivos = Depends(_get_registro_dispositivos),
) -> str:
    """Dependency de FastAPI: exige ``Authorization: Bearer <device_token>`` válido.

    Verifica, en orden: que el token esté presente, que su firma sea
    genuina (``verificar_firma_device_token``, criptografía pura) y que el
    dispositivo no esté revocado (``registro.esta_revocado``, requiere
    estado). Devuelve el ``device_id`` para que el endpoint lo use como
    identidad del llamador — el mismo rol que cumplía ``api_key`` antes de
    este cambio.
    """
    if credenciales is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta encabezado Authorization: Bearer <device_token>. "
            "Registra el dispositivo primero con POST /api/v1/dispositivos.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    device_id = verificar_firma_device_token(credenciales.credentials, settings)
    if device_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="device_token inválido.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if registro.esta_revocado(device_id):
        logger.warning("Request con dispositivo revocado: %s", device_id)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Dispositivo revocado.")

    registro.marcar_uso(device_id)
    return device_id


def _exigir_tasa_permitida(
    device_id: str = Depends(verificar_dispositivo),
    limitador: LimitadorTasaProtocolo = Depends(_get_limitador),
) -> str:
    """Dependency que aplica el rate limit antes de llegar al endpoint.

    Se resuelve *después* de ``verificar_dispositivo`` (FastAPI resuelve
    dependencias en el orden en que aparecen sus Depends) para no gastar
    cupo del limitador en requests que de todos modos van a rechazarse por
    no estar autenticadas o venir de un dispositivo revocado.
    """
    if not limitador.permitir(device_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Límite de mensajes por minuto excedido. Intenta de nuevo en breve.",
        )
    return device_id


def _exigir_consentimiento(
    request: Request,
    device_id: str = Depends(_exigir_tasa_permitida),
    registro: RegistroDispositivos = Depends(_get_registro_dispositivos),
) -> str:
    """Dependency que exige consentimiento explícito vigente antes de
    procesar un mensaje real.

    Solo se usa en los endpoints que envían contenido a un LLM y lo
    persisten (``/api/v1/mensajes*``) — no en registro de dispositivo,
    creación de sesión ni reinicio, que no procesan contenido sensible.
    Compara contra la versión ACTUAL del aviso (``Settings.
    aviso_privacidad_version``), no solo si alguna vez aceptó algo: si el
    aviso cambió después de que el usuario aceptó una versión anterior, el
    consentimiento antiguo ya no cuenta (ver
    ``docs/compliance/DPIA.md`` §4).
    """
    settings: Settings = request.app.state.settings
    version_aceptada = registro.obtener_version_consentimiento(device_id)
    if version_aceptada != settings.aviso_privacidad_version:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "consentimiento_requerido: acepta el aviso de privacidad vigente "
                f"(versión {settings.aviso_privacidad_version}) con "
                "POST /api/v1/dispositivos/consentimiento antes de enviar mensajes. "
                "Ver GET /privacidad para el contenido a mostrar."
            ),
        )
    return device_id


# --- Schemas ---------------------------------------------------------------


class DispositivoRegistrado(BaseModel):
    device_id: str
    device_token: str


class SesionCreada(BaseModel):
    session_id: str


class MensajeEntrada(BaseModel):
    mensaje: str = Field(..., min_length=1, max_length=4000)
    session_id: str


class ConsentimientoEntrada(BaseModel):
    version: str
    """Versión del aviso de privacidad que el cliente mostró y el usuario
    aceptó explícitamente (ver GET /privacidad → "version"). Debe coincidir
    con la versión vigente del servidor para habilitar el envío de
    mensajes — ver ``_exigir_consentimiento``."""


class RespuestaSalida(BaseModel):
    respuesta: str
    emocion: Optional[str] = None
    """Emoción predominante detectada en el mensaje del creyente (ver
    vocabulario en flow.json / prompts.py: amor, miedo, gratitud, tristeza,
    alegria, esperanza, devocion, desesperacion, ninguna), o ``None`` si no
    se pudo determinar. Pensado para que el cliente module intensidad
    visual gradual en vez de un disparador binario."""


class ErrorSalida(BaseModel):
    detail: str


# --- Router ------------------------------------------------------------


def _router() -> APIRouter:
    router = APIRouter()

    @router.get("/health", tags=["operación"])
    def health() -> dict:
        """Liveness: el proceso responde. No implica que el motor de IA esté sano."""
        return {"status": "ok"}

    @router.get("/health/ready", tags=["operación"])
    def readiness(request: Request) -> JSONResponse:
        """Readiness: refleja si el motor de IA está operando degradado.

        Antes, un flow de CrewAI que fallaba al cargar quedaba en modo
        fallback-solamente de forma silenciosa (solo visible en logs). Este
        endpoint lo hace observable por un orquestador (Kubernetes, un
        healthcheck de load balancer) para sacar la instancia de rotación
        o alertar, en vez de servir tráfico degradado indefinidamente sin
        que nadie se entere.
        """
        api: APILaSantisima = request.app.state.api
        degradado = getattr(api.caso_de_uso.servicio_respuestas, "esta_degradado", False)
        if degradado:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "degraded", "detail": "Motor de IA operando en modo fallback."},
            )
        return JSONResponse(content={"status": "ready"})

    @router.get("/privacidad", tags=["privacidad"])
    def aviso_privacidad() -> dict:
        """Aviso de privacidad servible por la ventana principal antes del primer mensaje.

        Contenido completo y editable en docs/privacidad.md (servido tal
        cual en GET /privacidad/documento); este endpoint devuelve un
        resumen apto para mostrarse en la UI sin que el cliente tenga que
        parsear Markdown.
        """
        settings = get_settings()
        # "Se guardan cifrados" solo si SANTISIMA_CLAVE_CIFRADO está
        # configurada de verdad (ver Settings.clave_cifrado): afirmarlo
        # incondicionalmente sería decirle al usuario algo falso en un
        # despliegue sin esa variable, justo sobre el dato que se le pide
        # aceptar.
        estado_cifrado = (
            "Se guardan cifrados" if settings.clave_cifrado else "Se guardan SIN cifrar"
        )
        return {
            "resumen": (
                "Tus mensajes pueden reflejar creencias y estado emocional. "
                f"{estado_cifrado}, se envían a un proveedor de IA (DeepInfra) "
                "para generar respuesta, y se conservan por un periodo limitado "
                "(ver retención). Puedes borrar tu conversación en cualquier "
                "momento."
            ),
            "version": settings.aviso_privacidad_version,
            "retencion_dias": settings.retencion_dias,
            "documento_completo": "/privacidad/documento",
        }

    @router.get("/privacidad/documento", tags=["privacidad"])
    def aviso_privacidad_documento() -> PlainTextResponse:
        """Sirve docs/privacidad.md tal cual — el documento completo detrás
        del resumen de GET /privacidad.

        Deliberadamente NO se monta todo ``docs/`` como estático: esa
        carpeta también tiene documentos internos de compliance (DPIA,
        RoPA, gobernanza) que nunca deben quedar públicos — solo este
        archivo se expone, explícitamente.
        """
        try:
            contenido = _RUTA_AVISO_PRIVACIDAD.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.error(
                "docs/privacidad.md no encontrado en %s: despliegue incompleto.",
                _RUTA_AVISO_PRIVACIDAD,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Aviso de privacidad no disponible en este servidor.",
            )
        return PlainTextResponse(content=contenido, media_type="text/markdown; charset=utf-8")

    @router.post(
        "/api/v1/dispositivos",
        response_model=DispositivoRegistrado,
        responses={429: {"model": ErrorSalida}},
        tags=["identidad"],
    )
    def registrar_dispositivo(
        request: Request,
        _tasa: None = Depends(_exigir_tasa_registro),
    ) -> DispositivoRegistrado:
        """Da de alta un dispositivo nuevo. Sin autenticación: es el punto
        de entrada — la app lo llama una sola vez, en su primer uso, y
        guarda el device_token devuelto (almacenamiento seguro del
        dispositivo: Keychain en iOS, Keystore en Android) para todo lo
        demás. No se pide nombre, email ni ningún dato personal.

        Sí tiene un rate limit por IP (``_exigir_tasa_registro``, holgado a
        propósito): protege el cupo del LLM contra un bucle automatizado
        generando dispositivos, sin afectar el flujo real de un usuario
        (un solo registro, una sola vez).
        """
        settings: Settings = request.app.state.settings
        registro: RegistroDispositivos = request.app.state.registro_dispositivos
        device_id = registro.registrar()
        return DispositivoRegistrado(
            device_id=device_id, device_token=emitir_device_token(device_id, settings)
        )

    @router.post("/api/v1/dispositivos/consentimiento", status_code=204, tags=["identidad"])
    def aceptar_consentimiento(
        entrada: ConsentimientoEntrada,
        device_id: str = Depends(verificar_dispositivo),
        registro: RegistroDispositivos = Depends(_get_registro_dispositivos),
    ) -> None:
        """Registra que el dispositivo aceptó, de forma explícita, el aviso
        de privacidad vigente (ver GET /privacidad → "version") — requisito
        de consentimiento explícito y diferenciado para el tratamiento de
        dato sensible (creencia religiosa/estado emocional) antes de que el
        creyente pueda enviar su primer mensaje real. No implica enviar ni
        persistir ningún mensaje: el saludo de bienvenida que el cliente
        muestra junto a este paso no pasa por el motor de IA.
        """
        registro.registrar_consentimiento(device_id, entrada.version)

    @router.post("/api/v1/sesiones", response_model=SesionCreada, tags=["conversación"])
    def crear_sesion(
        request: Request,
        device_id: str = Depends(verificar_dispositivo),
    ) -> SesionCreada:
        """Emite un session_id nuevo, atado criptográficamente al dispositivo llamante.

        Sustituye a dejar que el cliente elija su propio session_id (ver
        ``infrastructure.security``): así nadie puede adivinar ni reutilizar
        el session_id de otro creyente.
        """
        settings: Settings = request.app.state.settings
        return SesionCreada(session_id=emitir_session_id(device_id, settings))

    def _validar_propiedad_sesion(session_id: str, device_id: str, settings: Settings) -> None:
        if not validar_session_id(session_id, device_id, settings):
            # 404 (no 403) a propósito: no confirmar si el session_id existe
            # y pertenece a otro, para no filtrar esa información a quien
            # intenta enumerar sesiones ajenas.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Sesión no encontrada."
            )

    @router.post(
        "/api/v1/mensajes",
        response_model=RespuestaSalida,
        responses={
            403: {"model": ErrorSalida},
            404: {"model": ErrorSalida},
            429: {"model": ErrorSalida},
        },
        tags=["conversación"],
    )
    def enviar_mensaje(
        entrada: MensajeEntrada,
        request: Request,
        device_id: str = Depends(_exigir_consentimiento),
    ) -> RespuestaSalida:
        settings: Settings = request.app.state.settings
        _validar_propiedad_sesion(entrada.session_id, device_id, settings)
        api: APILaSantisima = request.app.state.api
        respuesta = api.responder(entrada.mensaje, session_id=entrada.session_id)
        return RespuestaSalida(respuesta=respuesta.contenido, emocion=respuesta.emocion)

    @router.post(
        "/api/v1/mensajes/stream",
        responses={
            403: {"model": ErrorSalida},
            404: {"model": ErrorSalida},
            429: {"model": ErrorSalida},
        },
        tags=["conversación"],
    )
    def enviar_mensaje_stream(
        entrada: MensajeEntrada,
        request: Request,
        device_id: str = Depends(_exigir_consentimiento),
    ) -> StreamingResponse:
        settings: Settings = request.app.state.settings
        _validar_propiedad_sesion(entrada.session_id, device_id, settings)
        api: APILaSantisima = request.app.state.api

        def _generar() -> Iterator[str]:
            generador = api.responder_stream(entrada.mensaje, session_id=entrada.session_id)
            emocion: Optional[str] = None
            while True:
                try:
                    chunk = next(generador)
                except StopIteration as fin:
                    emocion = fin.value
                    break
                yield f"data: {chunk}\n\n"
            yield f"event: done\ndata: {json.dumps({'emocion': emocion})}\n\n"

        return StreamingResponse(_generar(), media_type="text/event-stream")

    @router.post("/api/v1/sesiones/{session_id}/reiniciar", status_code=204, tags=["conversación"])
    def reiniciar_sesion(
        session_id: str,
        request: Request,
        device_id: str = Depends(verificar_dispositivo),
    ) -> None:
        settings: Settings = request.app.state.settings
        _validar_propiedad_sesion(session_id, device_id, settings)
        api: APILaSantisima = request.app.state.api
        api.reiniciar_sesion(session_id)

    @router.post(
        "/admin/dispositivos/{device_id}/revocar",
        status_code=204,
        tags=["administración"],
        responses={401: {"model": ErrorSalida}},
    )
    def revocar_dispositivo(
        device_id: str,
        request: Request,
        _api_key: str = Depends(verificar_api_key),
    ) -> None:
        """Bloquea un dispositivo abusivo. Requiere API key de administración
        (nunca la usa la app de un usuario final) — ver ``Settings.api_keys``.
        """
        registro: RegistroDispositivos = request.app.state.registro_dispositivos
        registro.revocar(device_id)

    return router


app = crear_app()
