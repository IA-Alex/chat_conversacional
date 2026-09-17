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

import hashlib
import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Iterator, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from .. import crear_servicio
from ..config import Settings, get_settings
from ..infrastructure import metrics
from ..infrastructure.dispositivos import RegistroDispositivos
from ..infrastructure.logging_config import configurar_logging
from ..infrastructure.purga_estado import EstadoPurga, leer_estado
from ..infrastructure.rate_limit import LimitadorTasa, LimitadorTasaProtocolo
from ..infrastructure.security import (
    bearer_scheme,
    emitir_device_token,
    emitir_session_id,
    validar_session_id,
    verificar_api_key,
    verificar_firma_device_token,
)
from . import _estado_observabilidad as estado_observabilidad
from .api import APILaSantisima

logger = logging.getLogger(__name__)

# Ruta al aviso de privacidad completo (docs/privacidad.md), resuelta desde
# la ubicación del paquete (no del cwd) para que sea independiente de dónde
# se invoque uvicorn. Se sirve explícitamente vía GET /privacidad/documento
# — no se monta todo ``docs/`` como estático a propósito: esa carpeta
# también contiene documentos internos de compliance (DPIA, RoPA,
# gobernanza) que nunca deben quedar públicos.
_RUTA_AVISO_PRIVACIDAD = Path(__file__).resolve().parents[3] / "docs" / "privacidad.md"

# Frontend servido desde el propio backend, en el mismo origen que la API
# (127.0.0.1:8000 tanto para GET / como para POST /api/v1/...). Evita que
# quien abra el HTML directamente por file:// (Origin: null) choque contra
# CORS — al ser mismo origen, el navegador no aplica esa política en
# absoluto. Un solo archivo explícito, igual que _RUTA_AVISO_PRIVACIDAD: no
# se monta el repo como estático, que expondría .env y las bases sqlite.
_RUTA_FRONTEND = Path(__file__).resolve().parents[3] / "frontend" / "index_santa_flat.html"

# Imagen del panel del frontend, servida como archivo aparte en vez de
# incrustada como data: URI en el HTML. Antes vivía en base64 dentro de
# index_santa_flat.html (~3.2MB de texto en una sola línea): el navegador
# tenía que descargar y parsear todo el documento antes de poder pintar
# nada, sin beneficio de caché entre visitas ni entre despliegues. Como
# archivo aparte con encabezados de caché, se descarga en paralelo al HTML
# y persiste en el caché del navegador. Mismo criterio de archivo único
# explícito que _RUTA_FRONTEND: no se monta el repo como estático.
_RUTA_IMAGEN_DEIDAD = Path(__file__).resolve().parents[3] / "deidad_1.jpeg"


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


def _fingerprint_secreto(secreto: Optional[str]) -> str:
    """Hash corto y no reversible de ``session_secret``, solo para
    diagnóstico entre arranques — nunca el valor real en logs.

    Motivación concreta: ``session_secret`` puede venir de una variable de
    entorno realmente exportada en el shell, que en pydantic-settings le
    gana en silencio al valor de ``.env`` sin ningún aviso (precedencia
    estándar: entorno > archivo). Si eso pasa entre dos arranques del
    mismo checkout, TODO device_token/session_id emitido antes dejará de
    verificar después — el síntoma es "sesión inválida" o "dispositivo
    revocado" que no lo es, y sin esto, diagnosticarlo requiere emitir un
    token de prueba y compararlo a mano. Con esto basta con mirar si el
    fingerprint cambió entre dos líneas de log de arranque.
    """
    if not secreto:
        return "(sin configurar)"
    return hashlib.sha256(secreto.encode("utf-8")).hexdigest()[:8]


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
    # Estado de observabilidad fresco por instancia de app.
    #
    # Vive en ``app.state`` y no en una variable de módulo: ``http_api`` es un
    # singleton de módulo (uvicorn importa el módulo una vez), pero los tests
    # construyen la app varias veces en el mismo proceso y compartirían las
    # sesiones abiertas de la app anterior — un test que crea una sesión
    # dejaría a la siguiente viendo "1 sesión activa" desde el arranque. En
    # producción solo hay una app, así que esto es equivalente a no hacer nada.
    #
    # ``_ESTADO_OBS_DEFAULT`` (el objeto de módulo) se usa solo como respaldo
    # para los helpers que corren fuera de un request; los endpoints leen
    # ``request.app.state.estado_obs`` vía ``_estado``.
    app.state.estado_obs = estado_observabilidad.EstadoObservabilidad()
    _ESTADO_OBS_DEFAULT.set(app.state.estado_obs)
    logger.info(
        "Backend La Santísima Muerte listo (use_langchain=%s, postgres=%s, "
        "redis_rate_limit=%s, session_secret_fingerprint=%s).",
        settings.use_langchain,
        settings.usar_postgres,
        settings.usar_redis_rate_limit,
        _fingerprint_secreto(settings.session_secret),
    )
    yield


def _permitir_origen_propio(app: FastAPI, settings: Settings) -> None:
    """Permite el origen con el que el navegador alcanzó ESTE backend.

    Motivación (bug real de arranque): con ``API_BASE`` apuntando a
    ``http://127.0.0.1:8000`` y ``SANTISIMA_CORS_ORIGINS`` en
    ``http://localhost:3000``, abrir la app en ``http://localhost:8000``
    hacía cross-origin cada llamada. ``CORSMiddleware`` responde al
    preflight con 400 "Disallowed CORS origin" — un error de CORS se ve
    en el cliente igual que una caída de red, y la UI mostraba "Verifica
    tu conexión" con el backend perfectamente sano.

    Se recibe ``settings`` (y no se llama ``get_settings()`` aquí) para
    que los tests puedan construír la app con ajustes sustituidos vía
    ``app.state``/dependency overrides sin efectos de módulo.

    No se añade nada si ya hay un comodín (``*``): sería redundante.
    """
    origenes = set(settings.cors_origins)

    @app.middleware("http")
    async def _reflejar_origen_propio(request: Request, call_next):  # type: ignore[no-untyped-def]
        respuesta = await call_next(request)

        if "*" in origenes:
            return respuesta

        origen = request.headers.get("origin")
        if not origen:
            return respuesta

        if origen not in _origenes_loopback(request):
            # Origen de terceros: CORSMiddleware ya lo rechazó (400) y no
            # debe recibir ninguna cabecera que lo autorice.
            return respuesta

        # Ya viene autorizado por CORSMiddleware (allow_origin_regex);
        # este middleware solo deja la cabecera explícita para clientes
        # que inspeccionan la respuesta.
        respuesta.headers["Access-Control-Allow-Origin"] = origen
        respuesta.headers["Access-Control-Allow-Methods"] = "GET, POST"
        respuesta.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        respuesta.headers["Vary"] = "Origin"
        return respuesta


def _instrumentar_metricas(app: FastAPI) -> None:
    """Cuenta y cronometra cada request HTTP (Prometheus), por endpoint.

    Usa la plantilla de ruta (``request.scope["route"].path``, p. ej.
    ``/admin/dispositivos/{device_id}/revocar``) y no la URL real: con la
    URL real, cada device_id distinto crearía una serie temporal nueva
    (cardinalidad sin límite, el error clásico de instrumentación
    Prometheus). Solo está disponible DESPUÉS de que el routing resolvió
    la request (tras ``call_next``); antes de eso no hay ``route`` en el
    scope.
    """

    @app.middleware("http")
    async def _medir_request(request: Request, call_next):  # type: ignore[no-untyped-def]
        inicio = time.monotonic()
        respuesta = await call_next(request)
        duracion = time.monotonic() - inicio

        route = request.scope.get("route")
        endpoint = route.path if route is not None else request.url.path
        metrics.http_requests_total.labels(
            endpoint=endpoint, metodo=request.method, status=str(respuesta.status_code)
        ).inc()
        metrics.http_request_latency_seconds.labels(endpoint=endpoint).observe(duracion)
        return respuesta


def _origenes_loopback(request: Request) -> set:
    """Orígenes del propio backend alcanzable por loopback.

    ``localhost:8000`` y ``127.0.0.1:8000`` son el MISMO backend en la
    interfaz de loopback, pero el navegador los trata como orígenes
    distintos. Se aceptan los dos: siguen siendo la propia máquina.
    """
    puerto = request.url.port or 80
    esquema = request.url.scheme
    return {
        f"{esquema}://{request.url.netloc}",
        f"{esquema}://localhost:{puerto}",
        f"{esquema}://127.0.0.1:{puerto}",
    }


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
        # Orígenes de loopback (http://localhost:PUERTO y
        # http://127.0.0.1:PUERTO): son ESTE mismo backend, pero el
        # navegador los trata como orígenes distintos de aquel con el que
        # sirvió la página (GET /). Sin esta regla, abrir la app en
        # http://localhost:8000 mientras el frontend llama a
        # http://127.0.0.1:8000 hacía que CORSMiddleware respondiera al
        # preflight con 400 "Disallowed CORS origin"; el cliente lo ve
        # igual que una caída de red y mostraba "Verifica tu conexión" con
        # el backend sano.
        #
        # El regex es deliberadamente estricto: solo loopback literal y un
        # puerto numérico — nunca un host de red (un origen de terceros
        # sigue recibiendo 400, ver TestCorsOrigenPropio).
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # Deja la cabecera CORS explícita para los orígenes de loopback (ver
    # ``_permitir_origen_propio``). CORSMiddleware ya los autoriza por el
    # regex de arriba; esto lo hace observable en la respuesta.
    _permitir_origen_propio(app, settings)
    _instrumentar_metricas(app)

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
        metrics.rate_limit_exceeded_total.labels(tipo="registro").inc()
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
    genuina (``verificar_firma_device_token``, criptografía pura), que el
    ``device_id`` exista en el registro (``registro.existe``) y que no
    esté revocado (``registro.esta_revocado``). Devuelve el ``device_id``
    para que el endpoint lo use como identidad del llamador — el mismo rol
    que cumplía ``api_key`` antes de este cambio.

    "No existe" y "revocado" se distinguen a propósito (401 vs. 403): una
    firma genuina sin fila en el registro es un device_token huérfano —
    emitido por este backend en algún momento, pero apuntando a un
    registro que ya no lo tiene (p. ej. una base de datos de dispositivos
    restaurada o distinta) — no una revocación deliberada. El cliente
    (ver auto-recuperación en el frontend, que reacciona a 401) puede
    re-registrarse solo; una revocación real (403) nunca debe
    autocorregirse así, o el mecanismo de bloqueo de abuso no serviría de
    nada. Antes ambos casos colapsaban en el mismo 403 "revocado", lo que
    además dejaba un log engañoso (dispositivos que nunca fueron
    revocados, reportados como revocados).
    """
    if credenciales is None:
        metrics.auth_failures_total.labels(motivo="sin_token").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta encabezado Authorization: Bearer <device_token>. "
            "Registra el dispositivo primero con POST /api/v1/dispositivos.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    device_id = verificar_firma_device_token(credenciales.credentials, settings)
    if device_id is None:
        metrics.auth_failures_total.labels(motivo="firma_invalida").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="device_token inválido.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not registro.existe(device_id):
        metrics.auth_failures_total.labels(motivo="no_reconocido").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="device_token no reconocido.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if registro.esta_revocado(device_id):
        logger.warning("Request con dispositivo revocado: %s", device_id)
        metrics.auth_failures_total.labels(motivo="revocado").inc()
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
        metrics.rate_limit_exceeded_total.labels(tipo="mensajes").inc()
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


# --- Helpers de observabilidad -------------------------------------------

# Sesiones y transiciones de degradación viven en un objeto propio
# (_estado_observabilidad.py): necesitan estado mutable y el proyecto no usa
# ``global`` en ningún módulo. Ver ese archivo para el porqué de cada tope.
#
# Este es el estado por defecto del proceso. ``_lifespan`` lo reemplaza por
# el de la app concreta, así que el objeto real es siempre el que está en
# ``app.state.estado_obs`` — un contenedor de un elemento en vez de una
# variable reasignable, para no necesitar ``global`` al cambiarlo.
_ESTADO_OBS_DEFAULT = estado_observabilidad.ContenedorEstado()


def _registrar_sesion(session_id: str) -> None:
    """Marca una sesión como abierta y actualiza ``santisima_active_sessions``."""
    _ESTADO_OBS_DEFAULT.get().registrar_sesion(session_id, time.monotonic())


def _cerrar_sesion(session_id: str) -> None:
    """Cierra una sesión, observando su duración (``santisima_session_duration_seconds``)."""
    _ESTADO_OBS_DEFAULT.get().cerrar_sesion(session_id, time.monotonic())


def _actualizar_estado_llm(degradado: bool) -> None:
    """Publica el gauge de degradación y cuenta las entradas a degradación."""
    _ESTADO_OBS_DEFAULT.get().actualizar_estado_llm(degradado)


def _payload_salud(
    settings: Settings,
    api: APILaSantisima,
    degradado: bool,
    estado_purga: Optional[EstadoPurga],
) -> dict:
    """Cuerpo de ``GET /metrics/health``.

    Extraído del endpoint (que solo orquesta) para no cruzar el límite de
    sentencias que el proyecto se impone por función: la ruta HTTP se lee
    como "leer estado, publicar gauges, devolver payload", y la construcción
    del payload —que es la parte que crece cuando se suma un campo nuevo—
    vive aparte.
    """
    backend = "postgres" if settings.usar_postgres else "sqlite"
    filas_historial = _contar_filas_historial(api, backend)
    if filas_historial is not None:
        metrics.db_historial_filas.labels(backend=backend).set(filas_historial)

    return {
        "llm_adapter_status": "degraded" if degradado else "ok",
        "db_backend": backend,
        # Mismo dato que la métrica Prometheus ``santisima_db_connections_active``
        # (ver infrastructure/metrics.py y el ``_conexion`` de
        # PostgresConversationRepository): conexiones contra la BD en este
        # instante. En sqlite siempre 0 — no hay servidor con el que abrir
        # conexiones concurrentes (``sqlite3`` es un archivo, serializado por
        # un lock del propio repositorio).
        "db_connection_pool_active_connections": (
            int(metrics.db_connections_active.labels(backend="postgres")._value.get())
            if settings.usar_postgres
            else 0
        ),
        "db_historial_filas": filas_historial,
        "sesiones_activas": _ESTADO_OBS_DEFAULT.get().sesiones_activas,
        "redis_rate_limit_enabled": settings.usar_redis_rate_limit,
        "redis_connection_status": _estado_redis(settings),
        "ultima_purga": estado_purga,
    }


def _contar_filas_historial(api: APILaSantisima, backend: str) -> Optional[int]:
    """Filas del historial vía el repositorio, tolerando backends sin soporte.

    Devuelve ``None`` (en vez de 0) cuando el repositorio no implementa
    ``contar_filas`` — p. ej. ``ConversationRepositoryMemory`` en desarrollo,
    o un doble de test. Cero y "no sé" son estados distintos: publicar 0
    haría creer que la base está vacía, cuando en realidad no se consultó.
    """
    repositorio = api.caso_de_uso.repositorio
    contar = getattr(repositorio, "contar_filas", None)
    if contar is None:
        return None
    try:
        return int(contar())
    except Exception:  # noqa: BLE001 — métrica de diagnóstico, nunca debe tumbar el endpoint
        logger.warning(
            "No se pudo contar las filas del historial (backend=%s).", backend, exc_info=True
        )
        return None


def _publicar_gauges_purga(settings: Settings) -> Optional[EstadoPurga]:
    """Lee el resultado de la purga y publica sus gauges. Devuelve el estado.

    La purga corre en OTRO proceso (systemd timer, cron o
    ``docker-compose.purga.yml`` — ver docs/despliegue.md §7), así que no
    puede tocar las métricas de este. El script deja el resultado en un
    archivo JSON y aquí se traduce a gauges en cada scrape; si la purga deja
    de correr, el timestamp simplemente deja de avanzar, y eso es lo que
    dispara ``SantisimaPurgaRetencionAtrasada``.
    """
    try:
        estado_purga = leer_estado(Path(settings.purga_estado_path))
    except OSError:  # noqa: BLE001 — métrica de diagnóstico, nunca debe tumbar el endpoint
        logger.warning("No se pudo leer el estado de purga.", exc_info=True)
        return None
    if estado_purga is not None:
        metrics.purga_ultimo_exito_timestamp.set(estado_purga["timestamp"])
        metrics.purga_ultimo_registros_borrados.set(estado_purga["registros_borrados"])
    return estado_purga


def _estado_redis(settings: Settings) -> str:
    """PING al Redis del rate limiter compartido. Devuelve un estado legible.

    Se delega en ``_estado_observabilidad.estado_redis`` (misma lógica,
    módulo cohesionado con el resto de la observabilidad).
    """
    return estado_observabilidad.estado_redis(settings)


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


def _registrar_rutas_privacidad(router: APIRouter) -> None:
    """Registra los dos endpoints de aviso de privacidad en ``router``.

    Extraído de ``_router()`` para mantener esa función bajo el límite de
    sentencias que el proyecto se impone: ``_router()`` agrupa cinco familias
    de endpoints (operación, privacidad, identidad, conversación,
    administración) y el aviso de privacidad es la única que no depende de
    ningún estado de la app — se lee de un archivo y de ``Settings``.
    """

    @router.get("/privacidad", tags=["privacidad"])
    def aviso_privacidad() -> dict:
        """Aviso de privacidad servible por la ventana principal antes del primer mensaje.

        Contenido completo y editable en docs/privacidad.md (servido tal
        cual en GET /privacidad/documento); este endpoint devuelve un
        resumen apto para mostrarse en la UI sin que el cliente tenga que
        parsear Markdown.
        """
        settings = get_settings()
        # "se cifran" solo si SANTISIMA_CLAVE_CIFRADO está configurada de
        # verdad (ver Settings.clave_cifrado): afirmarlo incondicionalmente
        # sería decirle al usuario algo falso en un despliegue sin esa
        # variable, justo sobre el dato que se le pide aceptar.
        estado_cifrado = "se cifran" if settings.clave_cifrado else "se guardan SIN cifrar"
        return {
            "resumen": (
                "Tus mensajes pueden reflejar creencias y estado emocional. "
                f"{estado_cifrado}, se envían a DeepInfra (IA) "
                "para responder, y se conservan por tiempo limitado. Puedes "
                "borrar tu conversación cuando quieras."
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


def _router() -> APIRouter:
    router = APIRouter()

    @router.get("/", include_in_schema=False)
    def frontend() -> FileResponse:
        """Sirve el frontend en el mismo origen que la API.

        Con la página y ``POST /api/v1/...`` en el mismo host:puerto, el
        navegador nunca dispara una petición cross-origin — CORS deja de
        aplicar y ``SANTISIMA_CORS_ORIGINS`` no necesita saber nada sobre
        cómo se sirve el HTML. Sigue existiendo el otro camino (servir el
        HTML desde ``python -m http.server`` en otro puerto, permitido vía
        CORS); este es el que no puede romperse abriendo el archivo con
        doble clic.
        """
        if not _RUTA_FRONTEND.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Frontend no disponible en este despliegue.",
            )
        return FileResponse(_RUTA_FRONTEND, media_type="text/html; charset=utf-8")

    @router.get("/assets/deidad.jpg", include_in_schema=False)
    def imagen_deidad() -> FileResponse:
        """Imagen del panel, servida aparte del HTML para que el navegador
        la cachee entre visitas (ver comentario de ``_RUTA_IMAGEN_DEIDAD``).
        """
        if not _RUTA_IMAGEN_DEIDAD.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Imagen no disponible en este despliegue.",
            )
        return FileResponse(
            _RUTA_IMAGEN_DEIDAD,
            media_type="image/jpeg",
            # Sin querystring de versión en la URL, "immutable" sería
            # peligroso: un reemplazo futuro del archivo nunca se vería
            # hasta que expirara el caché. Un día es suficiente para que
            # navegaciones repetidas en la misma sesión no re-descarguen
            # 2.4MB, sin comprometerse a un año de caché sobre una URL que
            # puede cambiar de contenido.
            headers={"Cache-Control": "public, max-age=86400"},
        )

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
        # ``_actualizar_estado_llm`` (y no ``metrics.llm_degradado.set``
        # directo) para que este endpoint — que es el que un orquestador
        # llama cada pocos segundos — también cuente las transiciones a
        # degradado en ``santisima_llm_degradation_events_total``.
        _actualizar_estado_llm(degradado)
        if degradado:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "degraded", "detail": "Motor de IA operando en modo fallback."},
            )
        return JSONResponse(content={"status": "ready"})

    @router.get("/metrics", tags=["operación"], include_in_schema=False)
    def metricas_prometheus() -> PlainTextResponse:
        """Métricas en formato de exposición de Prometheus (``text/plain``).

        Sin autenticación a propósito: es el mismo criterio que ``/health``
        — un scraper Prometheus/CloudWatch Agent no tiene por qué portar un
        device_token, y estas métricas no exponen contenido de
        conversaciones ni identificadores de usuario (ver
        ``infrastructure.metrics``: solo contadores agregados). Si el
        despliegue lo requiere, restringir el acceso es responsabilidad del
        proxy/red (no exponer el puerto a internet), no de este endpoint.
        """
        return PlainTextResponse(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @router.get("/metrics/health", tags=["operación"])
    def salud_detallada(request: Request) -> dict:
        """Resumen de salud en JSON, pensado para un dashboard/runbook
        humano (a diferencia de ``/metrics``, pensado para un scraper).

        Ver docs/runbooks/HEALTH_CHECKS.md para qué significa cada campo.
        """
        settings: Settings = request.app.state.settings
        api: APILaSantisima = request.app.state.api
        degradado = getattr(api.caso_de_uso.servicio_respuestas, "esta_degradado", False)
        estado_purga = _publicar_gauges_purga(settings)
        # Contadores de degradación: se derivan del estado, no del adapter,
        # que solo expone su estado ACTUAL (``esta_degradado``) — la
        # transición 0->1 se detecta comparando con el último valor
        # publicado. Ver EstadoObservabilidad.actualizar_estado_llm.
        _actualizar_estado_llm(degradado)
        return _payload_salud(settings, api, degradado, estado_purga)

    _registrar_rutas_privacidad(router)

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
        session_id = emitir_session_id(device_id, settings)
        _registrar_sesion(session_id)
        return SesionCreada(session_id=session_id)

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
        metrics.messages_total.inc()
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

        def _codificar_evento_sse(chunk: str) -> str:
            # Un valor `data:` multilínea debe llevar el prefijo en CADA
            # línea (spec SSE): un chunk que contenga "\n\n" (p. ej. un
            # salto de párrafo del LLM, o el aviso de corte de conexión de
            # más abajo) rompe el framing si se manda como `f"data:
            # {chunk}\n\n"` — el "\n\n" interno cierra el bloque a mitad de
            # camino y el resto llega sin prefijo `data:`, así que el
            # parser del cliente lo descarta en silencio.
            return "".join(f"data: {linea}\n" for linea in chunk.split("\n")) + "\n"

        def _generar() -> Iterator[str]:
            generador = api.responder_stream(entrada.mensaje, session_id=entrada.session_id)
            emocion: Optional[str] = None
            while True:
                try:
                    chunk = next(generador)
                except StopIteration as fin:
                    emocion = fin.value
                    break
                yield _codificar_evento_sse(chunk)
            metrics.messages_total.inc()
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
        _cerrar_sesion(session_id)

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
        metrics.device_revocations_total.inc()

    return router


app = crear_app()
