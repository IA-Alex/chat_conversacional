"""
Capa de presentación - API/Interfaz

Contiene los puntos de entrada para interactuar con la aplicación.
Soporta SSE (Server-Sent Events) para streaming de respuestas.
"""

from typing import Generator, Optional

from ..application import CasoDeUsoResponderMensaje
from ..domain import MensajeCreyente, RespuestaLaSantisima


class APILaSantisima:
    """API principal para interactuar con el servicio.

    Sigue el Principio de Inversión de Dependencias (DIP):
    las dependencias se inyectan desde el exterior, no se hardcodean.
    """

    def __init__(
        self,
        caso_de_uso: CasoDeUsoResponderMensaje,
    ):
        """
        Args:
            caso_de_uso: Instancia del caso de uso listo para usar.
                         El creador (factory) es responsable de ensamblar
                         las dependencias (adapter, repositorio).
        """
        self.caso_de_uso = caso_de_uso

    def responder(self, mensaje: str, session_id: str = "default") -> RespuestaLaSantisima:
        """
        Punto de entrada principal (sin streaming):
        - Recibe un mensaje del creyente y un session_id
        - Devuelve la respuesta de La Santísima Muerte (contenido, modelo,
          emoción detectada)
        """
        return self.caso_de_uso.ejecutar(mensaje, session_id=session_id)

    def responder_stream(
        self,
        mensaje: str,
        session_id: str = "default",
    ) -> Generator[str, None, Optional[str]]:
        """
        Punto de entrada con streaming (SSE):
        - Recibe un mensaje del creyente y un session_id
        - Streamea la respuesta token a token
        - El usuario ve texto en milisegundos
        - El valor de retorno del generador lleva la emoción detectada
          (ver ``CasoDeUsoResponderMensaje.ejecutar_stream``)
        """
        emocion = yield from self.caso_de_uso.ejecutar_stream(mensaje, session_id=session_id)
        return emocion

    def reiniciar_sesion(self, session_id: str) -> None:
        """Reinicia el historial de una sesión."""
        self.caso_de_uso.repositorio.clear_history(session_id)
