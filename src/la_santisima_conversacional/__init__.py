"""
Módulo principal La Santísima Muerte Conversacional

Expone la interfaz pública del paquete
"""

import os
from typing import Optional, TYPE_CHECKING
from pathlib import Path

from .domain import ConversationRepository, ServicioLaSantisima

if TYPE_CHECKING:
    from .presentation.api import APILaSantisima


def _get_api_la_santisima() -> type:
    from .presentation.api import APILaSantisima as _APILaSantisima

    return _APILaSantisima


def __getattr__(name: str) -> object:
    if name == "APILaSantisima":
        return _get_api_la_santisima()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def crear_servicio(
    flow_path: Optional[str] = None,
    use_langchain: bool = True,
    langchain_model: str = "openai/google/gemma-4-31B-it-turbo",
    modelo_chat: str = "openai/google/gemma-4-31B-it-turbo",
    modelo_resumen: str = "openai/google/gemma-4-26B-A4B-it",
    modelo_clasificador: str = "openai/deepseek-ai/DeepSeek-V4-Flash-0731",
    ventana_mensajes: int = 10,
    repositorio: Optional[ConversationRepository] = None,
    usar_sqlite: bool = False,
    sqlite_db_path: str = "conversations.db",
    usar_postgres: bool = False,
    postgres_dsn: Optional[str] = None,
    clave_cifrado: Optional[str] = None,
    retencion_dias: int = 90,
    deepinfra_api_key: Optional[str] = None,
    deepinfra_api_base: str = "https://api.deepinfra.com/v1/openai",
) -> "APILaSantisima":
    """
    Factory method para crear el servicio principal.

    Inyecta las dependencias correctas según el flag use_langchain.

    Args:
        flow_path: Ruta al archivo flow.json (solo para CrewAI).
        use_langchain: Si True, usa el adaptador LangChain (LCEL) en lugar
            de CrewAI. Ambos motores tienen paridad funcional: clasificación
            de intención/emoción, sliding window, memoria persistente y
            degradación validada con fallback.
        langchain_model: Modelo principal a usar con LangChain (equivalente
            a modelo_chat, en formato "gpt-4o" u "openai/gpt-4o").
        modelo_chat: Modelo para generar respuestas (CrewAI).
        modelo_resumen: Modelo para resúmenes en background (ambos motores).
        modelo_clasificador: Modelo para clasificar intención/emoción (ambos motores).
        ventana_mensajes: Tamaño de la ventana deslizante de historial (ambos motores).
        repositorio: Repositorio de conversaciones a usar. Si se provee,
            tiene prioridad sobre `usar_sqlite` y permite inyectar cualquier
            implementación de ConversationRepository (memoria, SQLite,
            futura Redis/Dynamo, etc.), respetando DIP.
        usar_sqlite: Si True (y no se pasó `repositorio`), usa
            SQLiteConversationRepository en vez del repositorio en memoria.
            Antes esta fábrica solo podía construir el backend en memoria,
            dejando inalcanzable en la práctica el backend "de producción"
            que la propia arquitectura documenta.
        sqlite_db_path: Ruta del archivo SQLite cuando `usar_sqlite=True`.
        usar_postgres: Si True (y no se pasó `repositorio`), usa
            PostgresConversationRepository en vez de SQLite/memoria. Tiene
            prioridad sobre `usar_sqlite`. Necesario para correr más de una
            instancia del backend a la vez (ver README "Escalar a múltiples
            instancias"); requiere el extra `postgres` instalado.
        postgres_dsn: Cadena de conexión de Postgres. Requerido si
            `usar_postgres=True`.
        clave_cifrado: Clave Fernet para cifrar el historial en reposo
            (SQLite o Postgres). Ver `SQLiteConversationRepository`.
        retencion_dias: Días de retención del historial (SQLite o Postgres).
        deepinfra_api_key: Key de DeepInfra (proveedor real del modelo).
            Si se provee, se usa para poblar `OPENAI_API_KEY`/
            `OPENAI_API_BASE` en el proceso antes de construir los
            adaptadores: tanto el flow de CrewAI (vía LiteLLM) como
            `LangChainAdapter` (vía `ChatOpenAI`) leen esas variables de
            entorno estándar sin necesidad de tocar su código interno — solo
            cambia a qué endpoint apuntan. Si no se provee, se asume que el
            entorno ya las tiene configuradas (p. ej. en tests).
        deepinfra_api_base: Endpoint compatible con OpenAI de DeepInfra.

    Returns:
        Instancia configurada de APILaSantisima con soporte de streaming,
        sliding window y memoria asíncrona.
    """
    from .application import CasoDeUsoResponderMensaje

    if deepinfra_api_key:
        # Único punto del proceso donde se traduce nuestra key de DeepInfra
        # al nombre de variable que el SDK de OpenAI (y LiteLLM, que usa el
        # mismo SDK por debajo) espera. Ni CrewAIAdapter ni LangChainAdapter
        # necesitan saber que el proveedor real es DeepInfra.
        os.environ["OPENAI_API_KEY"] = deepinfra_api_key
        os.environ["OPENAI_API_BASE"] = deepinfra_api_base
        os.environ["OPENAI_BASE_URL"] = deepinfra_api_base

    if repositorio is None:
        if usar_postgres:
            if not postgres_dsn:
                raise ValueError("usar_postgres=True requiere postgres_dsn.")
            from .infrastructure.repositories import PostgresConversationRepository

            repositorio = PostgresConversationRepository(
                dsn=postgres_dsn,
                clave_cifrado=clave_cifrado,
                retencion_dias=retencion_dias,
            )
        elif usar_sqlite:
            from .infrastructure.repositories import SQLiteConversationRepository

            repositorio = SQLiteConversationRepository(
                db_path=sqlite_db_path,
                clave_cifrado=clave_cifrado,
                retencion_dias=retencion_dias,
            )
        else:
            from .infrastructure.repositories import ConversationRepositoryMemory

            repositorio = ConversationRepositoryMemory()

    servicio: ServicioLaSantisima
    if use_langchain:
        from .infrastructure.langchain_adapter import LangChainAdapter

        # modelo_resumen/modelo_clasificador/ventana_mensajes antes solo se
        # pasaban al adaptador de CrewAI: LangChainAdapter los ignoraba por
        # completo (no tenía clasificación de intención ni memoria
        # persistente). Ahora ambos adaptadores comparten el mismo
        # contrato de configuración.
        servicio = LangChainAdapter(
            model=langchain_model,
            modelo_resumen=modelo_resumen,
            modelo_clasificador=modelo_clasificador,
            ventana_mensajes=ventana_mensajes,
        )
    else:
        if flow_path is None:
            flow_path = str(Path(__file__).parent / "infrastructure" / "flow.json")
        from .infrastructure.crewai_adapter import CrewAILaSantisimaAdapter

        servicio = CrewAILaSantisimaAdapter(
            flow_path=flow_path,
            modelo_chat=modelo_chat,
            modelo_resumen=modelo_resumen,
            modelo_clasificador=modelo_clasificador,
            ventana_mensajes=ventana_mensajes,
        )

    caso_de_uso = CasoDeUsoResponderMensaje(servicio, repositorio)
    from .presentation.api import APILaSantisima as _APILaSantisima

    return _APILaSantisima(caso_de_uso=caso_de_uso)


__all__ = ["crear_servicio", "APILaSantisima"]
