"""Configuración centralizada del backend (12-factor: config vía entorno).

Antes cada capa (factory, adapters, futura API) leía variables de entorno
o hardcodeaba defaults por su cuenta (p. ej. ``"openai/gpt-4o"`` repetido
en tres sitios distintos), y nada validaba al arrancar que
``DEEPINFRA_API_KEY`` existiera: el primer síntoma de una key faltante era
un error de autenticación en la primera llamada al LLM, con el proceso ya
atendiendo tráfico. ``Settings`` centraliza esa configuración y falla al
arrancar (fail-fast) si falta algo requerido.

Todas las variables se leen con prefijo ``SANTISIMA_`` para no colisionar
con variables de otros procesos en el mismo entorno (excepto
``DEEPINFRA_API_KEY``, con su propio nombre porque identifica al
proveedor real del modelo, igual que antes lo hacía ``OPENAI_API_KEY``).

El proveedor de IA es DeepInfra (https://deepinfra.com), servido a través
de su endpoint compatible con la API de OpenAI: ``crear_servicio``
(``__init__.py``) usa ``deepinfra_api_key``/``deepinfra_api_base`` para
poblar ``OPENAI_API_KEY``/``OPENAI_API_BASE`` en el proceso antes de
construir los adaptadores, que siguen usando el SDK/LiteLLM de OpenAI sin
cambios — solo apuntan a otra base URL. Los nombres de modelo mantienen
el prefijo ``"openai/"`` (convención LiteLLM) seguido del id real del
modelo en DeepInfra, p. ej. ``"openai/google/gemma-4-31B-it-turbo"``.
"""

from functools import lru_cache
from typing import Annotated, List, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración de todo el backend, validada al arrancar el proceso."""

    model_config = SettingsConfigDict(
        env_prefix="SANTISIMA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Permite construir Settings(openai_api_key=...) por nombre de
        # campo Python además de por su alias de entorno ("OPENAI_API_KEY"):
        # los tests instancian Settings directamente con kwargs, sin pasar
        # por variables de entorno.
        populate_by_name=True,
    )

    # --- Motor de IA (DeepInfra, vía su endpoint compatible con OpenAI) ---
    deepinfra_api_key: str = Field(..., alias="DEEPINFRA_API_KEY")
    deepinfra_api_base: str = "https://api.deepinfra.com/v1/openai"
    """Endpoint compatible con la API de OpenAI que expone DeepInfra. Rara
    vez necesita cambiarse; existe como campo (y no una constante) para
    poder apuntar a otra región/proxy sin tocar código."""
    use_langchain: bool = True
    modelo_chat: str = "openai/google/gemma-4-31B-it-turbo"
    """Genera la respuesta devocional principal. Variante "turbo" de Gemma
    4 31B: mismos pesos que la variante estándar, optimizada para latencia
    y más barata — prioridad explícita del proyecto sobre degradar la
    experiencia del creyente."""
    modelo_resumen: str = "openai/google/gemma-4-26B-A4B-it"
    """Resume la memoria persistente en background. MoE 26B (4B activos),
    corre a velocidad cercana a un modelo denso de 4B con más conocimiento
    accesible — suficiente para compresión de historial sin el costo del
    modelo principal."""
    modelo_clasificador: str = "openai/deepseek-ai/DeepSeek-V4-Flash-0731"
    """Clasifica intención/emoción (salida corta y estructurada). Tarea de
    bajo riesgo si el modelo se equivoca ocasionalmente (no es la voz que
    llega al creyente), así que se prioriza el modelo más económico del
    grupo evaluado."""
    ventana_mensajes: int = 10
    llm_timeout_segundos: float = 20.0
    llm_max_reintentos: int = 2

    # --- Persistencia ---
    usar_sqlite: bool = True
    sqlite_db_path: str = "conversations.db"
    usar_postgres: bool = False
    """Si True, usa PostgresConversationRepository en vez de SQLite. Tiene
    prioridad sobre usar_sqlite. Requerido para correr más de una instancia
    del backend a la vez (ver README "Escalar a múltiples instancias").
    Apagado por defecto: no obliga a tener Postgres corriendo."""
    postgres_dsn: Optional[str] = None
    """Cadena de conexión, p. ej. postgresql://usuario:password@host:5432/db.
    Requerido si usar_postgres=True."""
    retencion_dias: int = 90
    """Días que se conservan los mensajes antes de purgarse (ver
    ``purgar_expirados`` en ``SQLiteConversationRepository``). Parte de la
    política de minimización de datos: antes no existía ningún límite de
    retención y la base crecía indefinidamente con datos sensibles."""
    clave_cifrado: Optional[str] = None
    """Clave Fernet (44 chars, urlsafe-base64) para cifrar el contenido de
    los mensajes en reposo. Si es None, se guarda en texto plano (aceptable
    solo en desarrollo local). Generar con
    ``cryptography.fernet.Fernet.generate_key()``."""

    # --- Identidad de dispositivo (usuarios finales de la app) ---
    purga_estado_path: str = "purga_estado.json"
    """Archivo donde ``scripts/purgar_retencion.py`` registra el resultado
    de su última ejecución (timestamp, filas borradas, éxito), leído por
    ``GET /metrics/health`` para detectar si la purga dejó de correr."""

    dispositivos_db_path: str = "dispositivos.db"
    """SQLite donde se registra qué dispositivos existen y cuáles fueron
    revocados (ver ``infrastructure.dispositivos``). Tabla separada de la
    de conversaciones a propósito: identidad/abuso y contenido
    conversacional tienen ciclos de vida distintos."""

    # --- Seguridad HTTP ---
    # NoDecode: por defecto pydantic-settings intenta parsear cualquier
    # List[...] leído de variables de entorno como JSON antes de que
    # nuestro validador "before" corra, así que "a,b,c" fallaría con un
    # error de parseo. NoDecode entrega el string crudo al validador.
    api_keys: Annotated[List[str], NoDecode] = Field(default_factory=list)
    """API keys de ADMINISTRACIÓN (revocar dispositivos, etc.) — nunca las
    usa la app de un usuario final; esa usa device_token, emitido por
    ``POST /api/v1/dispositivos`` sin necesitar ninguna API key. Puede
    quedar vacío: solo significa que los endpoints de admin rechazan todo
    (no bloquea el arranque ni el uso normal de la app)."""
    session_secret: Optional[str] = None
    """Secreto HMAC para firmar/validar session_id y device_token emitidos
    por el servidor (ver ``infrastructure.security``). Obligatorio salvo
    en modo debug."""
    debug: bool = False
    """Modo desarrollo: permite arrancar sin api_keys/session_secret y
    relaja CORS. Nunca debe estar activo en producción."""
    confirmo_debug_en_prod: bool = False
    """Confirmación explícita de que debug está activo intencionalmente en 
    un entorno que parece producción. Si debug=true y se detectan señales de
    entorno productivo (KUBERNETES_SERVICE_HOST o SANTISIMA_ENTORNO=production),
    esta variable DEBE ser true, de lo contrario el arranque falla."""
    cors_origins: Annotated[List[str], NoDecode] = Field(default_factory=list)
    rate_limit_por_minuto: int = 20
    """Mensajes permitidos por API key por minuto. Ver
    ``infrastructure.rate_limit``."""
    rate_limit_registro_por_minuto: int = 10
    """Registros de dispositivo (``POST /api/v1/dispositivos``) permitidos
    por IP de origen por minuto. Este endpoint no tiene auth (es el punto
    de entrada de un usuario nuevo), así que sin límite propio es una
    factura abierta: cada registro exitoso arranca su propio cupo de
    ``rate_limit_por_minuto`` para el motor de IA, así que generarlos en
    bucle evade el rate limit de mensajes. El valor por defecto es
    deliberadamente holgado (un usuario real solo registra su dispositivo
    una vez; esto cubre reintentos por red inestable o varias pestañas)
    para no interrumpir nunca a un usuario legítimo — solo corta un bucle
    automatizado."""
    usar_redis_rate_limit: bool = False
    """Si True, usa LimitadorTasaRedis en vez del limitador en memoria.
    Necesario en cuanto corres más de una instancia del backend (ver
    README "Escalar a múltiples instancias"); con una sola instancia, el
    limitador en memoria es correcto y no requiere Redis corriendo."""
    redis_url: Optional[str] = None
    """p. ej. redis://localhost:6379/0. Requerido si usar_redis_rate_limit=True."""
    max_longitud_mensaje: int = 4000

    # --- Consentimiento ---
    aviso_privacidad_version: str = "v1"
    """Identificador de la versión vigente de ``docs/privacidad.md``. Un
    dispositivo solo puede enviar mensajes si aceptó ESTA versión exacta
    (ver ``POST /api/v1/dispositivos/consentimiento`` en ``http_api.py``):
    subir este valor al cambiar el aviso fuerza a todos los usuarios a
    re-aceptar, en vez de arrastrar silenciosamente un consentimiento dado
    a un texto que ya no es el vigente."""

    @field_validator("api_keys", "cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        """Permite pasar listas como CSV en variables de entorno (`"a,b,c"`)."""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @model_validator(mode="after")
    def _validar_coherencia_backends(self) -> "Settings":
        """Un flag ``usar_X=True`` sin su configuración de conexión es un
        error de configuración en sí mismo (no algo exclusivo de
        producción): falla aquí, no al primer request que lo necesite.
        """
        if self.usar_postgres and not self.postgres_dsn:
            raise ValueError("SANTISIMA_USAR_POSTGRES=true requiere SANTISIMA_POSTGRES_DSN.")
        if self.usar_redis_rate_limit and not self.redis_url:
            raise ValueError("SANTISIMA_USAR_REDIS_RATE_LIMIT=true requiere SANTISIMA_REDIS_URL.")
        return self

    @model_validator(mode="after")
    def _validar_debug_en_produccion(self) -> "Settings":
        """Valida que debug no esté activo en producción sin confirmación explícita.

        Detecta señales de entorno productivo y falla si debug=true sin
        confirmo_debug_en_prod=true.
        """
        if not self.debug:
            return self

        # Señales de entorno productivo
        import os

        en_kubernetes = "KUBERNETES_SERVICE_HOST" in os.environ
        entorno_produccion = os.environ.get("SANTISIMA_ENTORNO") == "production"

        if (en_kubernetes or entorno_produccion) and not self.confirmo_debug_en_prod:
            señales = []
            if en_kubernetes:
                señales.append("KUBERNETES_SERVICE_HOST presente")
            if entorno_produccion:
                señales.append("SANTISIMA_ENTORNO=production")

            raise ValueError(
                f"debug=true detectado en entorno productivo ({', '.join(señales)}). "
                "Establece SANTISIMA_CONFIRMO_DEBUG_EN_PROD=true si es intencional."
            )

        return self

    def validar_produccion(self) -> None:
        """Valida invariantes que solo se exigen fuera de modo debug.

        Se llama explícitamente al construir la app HTTP (no en el
        validador de pydantic) para que ``Settings`` siga siendo
        instanciable en tests unitarios sin tener que simular producción
        completa.
        """
        if self.debug:
            return
        # api_keys NO se exige aquí: son solo para administración y su
        # ausencia simplemente deja esos endpoints inalcanzables, no rompe
        # el uso normal de la app (que se identifica por dispositivo).
        if not self.session_secret:
            raise RuntimeError(
                "SANTISIMA_SESSION_SECRET no configurado: requerido para "
                "firmar session_id/device_token fuera de modo debug."
            )
        if not self.clave_cifrado:
            raise RuntimeError(
                "SANTISIMA_CLAVE_CIFRADO no configurado: requerido para "
                "cifrar contenido sensible fuera de modo debug."
            )


@lru_cache
def get_settings() -> Settings:
    """Punto único de acceso a la configuración (cacheado por proceso).

    Usar esta función (no instanciar ``Settings()`` directamente) en el
    resto del código, para que toda la app comparta la misma instancia y
    la validación de entorno ocurra una sola vez, al primer acceso.
    """
    return Settings()  # type: ignore[call-arg]
