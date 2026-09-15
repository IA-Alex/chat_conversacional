"""
Capa de aplicación - Casos de uso y servicios

Contiene la lógica de aplicación que coordina el flujo entre:
- La presentación (entrada/salida)
- El dominio (lógica de negocio)
- La infraestructura (implementaciones concretas)
"""

from datetime import datetime
from typing import Generator, List, Optional

from ..domain import (
    MensajeCreyente,
    RespuestaLaSantisima,
    ServicioLaSantisima,
    ConversationRepository,
    Message,
)


class CasoDeUsoResponderMensaje:
    """Caso de uso principal: recibe un mensaje del creyente y devuelve una respuesta.

    Coordina el flujo completo con optimizaciones de memoria:
    1. Recupera el historial de la sesión (incluye resumen persistente como mensaje system).
    2. Crea la entidad MensajeCreyente con session_id.
    3. Persiste el mensaje del usuario.
    4. Delega la generación al servicio (sliding window + resumen en system prompt).
    5. Persiste la respuesta y el nuevo resumen generado.
    6. Retorna el contenido de la respuesta.
    """

    def __init__(
        self,
        servicio_respuestas: ServicioLaSantisima,
        repositorio: ConversationRepository,
    ):
        self.servicio_respuestas = servicio_respuestas
        self.repositorio = repositorio

    def ejecutar(self, mensaje: str, session_id: str = "default") -> RespuestaLaSantisima:
        """Ejecuta el flujo completo de responder a un creyente (sin streaming)."""
        # 1. Recuperar historial previo de la sesión
        historial: List[Message] = self.repositorio.get_history(session_id)

        # 2. Crear entidad de dominio con session_id
        mensaje_creyente = MensajeCreyente(mensaje, session_id=session_id)

        # 3. Persistir el mensaje del usuario
        self.repositorio.save_message(
            session_id,
            Message(role="user", content=mensaje, timestamp=datetime.now()),
        )

        # 4. Generar respuesta con sliding window + resumen persistente.
        # on_resumen_actualizado persiste el nuevo resumen de memoria de largo
        # plazo que el servicio calcule (p. ej. tras "actualizar_memoria" en
        # el flow de CrewAI). Antes este resumen se calculaba y se descartaba:
        # nunca llegaba al repositorio, por lo que la conversación jamás
        # ganaba memoria persistente real entre turnos.
        respuesta = self.servicio_respuestas.responder_mensaje(
            mensaje=mensaje_creyente,
            historial=historial,
            on_resumen_actualizado=lambda resumen: self.repositorio.save_resumen(
                session_id, resumen
            ),
        )

        # 5. Persistir la respuesta
        self.repositorio.save_message(
            session_id,
            Message(
                role="assistant", 
                content=respuesta.contenido, 
                timestamp=datetime.now(),
                modelo=respuesta.modelo
            ),
        )

        # 6. Retornar
        return respuesta

    def ejecutar_stream(
        self,
        mensaje: str,
        session_id: str = "default",
    ) -> Generator[str, None, Optional[str]]:
        """Ejecuta el flujo completo con streaming vía SSE.

        El usuario empieza a ver texto en milisegundos.
        La respuesta se streamea token a token. El valor de retorno del
        generador (``StopIteration.value``, ver
        ``ServicioLaSantisima.responder_mensaje_stream``) lleva la emoción
        detectada, para que la capa de presentación la exponga en el
        evento SSE final sin mezclarla con los chunks de texto.
        """
        # 1. Recuperar historial (incluye resumen persistente como system)
        historial: List[Message] = self.repositorio.get_history(session_id)

        # 2. Crear entidad con session_id
        mensaje_creyente = MensajeCreyente(mensaje, session_id=session_id)

        # 3. Persistir el mensaje del usuario inmediatamente
        self.repositorio.save_message(
            session_id,
            Message(role="user", content=mensaje, timestamp=datetime.now()),
        )

        # 4. Generar respuesta en streaming (ver nota sobre on_resumen_actualizado
        # en ejecutar()): también aplica al camino de streaming, que antes
        # descartaba igualmente el resumen actualizado.
        respuesta_completa: list[str] = []
        generador = self.servicio_respuestas.responder_mensaje_stream(
            mensaje=mensaje_creyente,
            historial=historial,
            on_resumen_actualizado=lambda resumen: self.repositorio.save_resumen(
                session_id, resumen
            ),
        )
        emocion: Optional[str] = None
        while True:
            try:
                chunk = next(generador)
            except StopIteration as fin:
                emocion = fin.value
                break
            respuesta_completa.append(chunk)
            yield chunk

        # 5. Persistir la respuesta completa
        contenido_final = "".join(respuesta_completa)
        self.repositorio.save_message(
            session_id,
            Message(
                role="assistant",
                content=contenido_final,
                timestamp=datetime.now(),
                modelo="streaming"  # Modelo desconocido en streaming
            ),
        )

        return emocion
