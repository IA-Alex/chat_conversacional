"""
Interfaces y contratos del dominio.

Define los puertos (interfaces) que la capa de dominio expone para que
la infraestructura los implemente. Esto sigue el Principio de Inversión
de Dependencias (DIP): el dominio no conoce detalles de infraestructura.
"""

from typing import Callable, Generator, List, Optional, Protocol, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    # Import solo para chequeo estático (mypy); evita ciclos de import en runtime.
    from . import MensajeCreyente, RespuestaLaSantisima


class Message:
    """Representa un mensaje dentro del historial de conversación."""

    def __init__(
        self,
        role: str,
        content: str,
        timestamp: Optional[datetime] = None,
        modelo: Optional[str] = None,
    ):
        if role not in ("user", "assistant", "system"):
            raise ValueError(f"Role inválido: {role}. Debe ser user, assistant o system.")
        self.role = role
        self.content = content
        self.timestamp = timestamp or datetime.now()
        self.modelo = modelo  # Modelo que generó la respuesta (solo para role='assistant')

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Message):
            return NotImplemented
        return (
            self.role == other.role
            and self.content == other.content
            and self.timestamp == other.timestamp
            and self.modelo == other.modelo
        )

    def __repr__(self) -> str:
        return (
            f"Message(role={self.role!r}, content={self.content!r}, "
            f"timestamp={self.timestamp!r}, modelo={self.modelo!r})"
        )


class ConversationRepository(Protocol):
    """Contrato para el repositorio de conversaciones.

    Cualquier implementación concreta (SQLite, Redis, PostgreSQL, etc.)
    debe cumplir este protocolo para ser intercambiable sin afectar
    la lógica de negocio.
    """

    def get_history(self, session_id: str) -> List[Message]:
        """Recupera el historial completo de una sesión."""
        ...

    def save_message(self, session_id: str, message: Message) -> None:
        """Persiste un mensaje en el historial de la sesión."""
        ...

    def clear_history(self, session_id: str) -> None:
        """Elimina el historial completo de una sesión."""
        ...

    def get_resumen(self, session_id: str) -> str:
        """Recupera el resumen persistente (memoria de largo plazo) de una sesión."""
        ...

    def save_resumen(self, session_id: str, resumen: str) -> None:
        """Guarda o actualiza el resumen persistente de una sesión.

        Forma parte del contrato para que la actualización de memoria
        asíncrona del servicio (ver ``on_resumen_actualizado`` en
        :class:`ServicioLaSantisima`) pueda persistirse sin acoplar el
        caso de uso a una implementación concreta de repositorio.
        """
        ...


class ServicioLaSantisima(Protocol):
    """Contrato para el servicio de generación de respuestas.

    Define cómo el caso de uso interactúa con el motor de IA,
    ya sea LangChain, CrewAI u otro.
    """

    esta_degradado: bool
    """True si el motor quedó operando permanentemente en modo degradado
    (p. ej. el flow declarativo de CrewAI no pudo cargarse): solo entrega
    respuestas de fallback, sin clasificación de intención ni memoria
    persistente real. Expuesto para que un endpoint de salud (ver
    ``presentation.http_api``) pueda reportar el servicio como no-listo en
    vez de responder 200 mientras opera degradado en silencio.
    """

    def responder_mensaje(
        self,
        mensaje: "MensajeCreyente",
        historial: Optional[List[Message]] = None,
        on_resumen_actualizado: Optional[Callable[[str], None]] = None,
    ) -> "RespuestaLaSantisima":
        """Procesa un mensaje del creyente y devuelve una respuesta.

        Args:
            mensaje: Mensaje actual del creyente.
            historial: Historial previo de la conversación, si existe.
            on_resumen_actualizado: Callback opcional invocado con el nuevo
                resumen de memoria persistente cuando el servicio genera uno
                (p. ej. tras el paso de actualización de memoria del flow).
                El caso de uso lo usa para persistirlo sin que este servicio
                conozca el repositorio concreto. Implementaciones que no
                generan resumen (p. ej. LangChain puro) simplemente lo ignoran.

        Returns:
            Respuesta generada por el servicio.
        """
        ...

    def responder_mensaje_stream(
        self,
        mensaje: "MensajeCreyente",
        historial: Optional[List[Message]] = None,
        on_resumen_actualizado: Optional[Callable[[str], None]] = None,
    ) -> Generator[str, None, Optional[str]]:
        """Procesa un mensaje del creyente y streamea la respuesta token a token.

        Args:
            mensaje: Mensaje actual del creyente.
            historial: Historial previo de la conversación, si existe.
            on_resumen_actualizado: Ver :meth:`responder_mensaje`.

        Yields:
            Fragmentos de texto de la respuesta generada.

        Returns:
            La emoción predominante detectada en el mensaje del creyente
            (ver vocabulario en flow.json / prompts.py), o ``None`` si no
            se pudo determinar (p. ej. degradó a fallback). Se obtiene vía
            el valor de retorno del generador (``StopIteration.value``),
            no como un chunk más, para no alterar el streaming de texto.
        """
        ...


class LLMService(Protocol):
    """Contrato mínimo para un LLM que admite invocación y streaming.

    Permite que el fallback y otros componentes usen cualquier proveedor
    sin acoplarse a LangChain directamente.
    """

    def invoke(self, prompt: str, **kwargs: object) -> str:
        """Ejecuta un prompt y devuelve la respuesta completa."""
        ...

    def stream(self, prompt: str, **kwargs: object) -> Generator[str, None, None]:
        """Ejecuta un prompt y streamea la respuesta token a token."""
        ...
