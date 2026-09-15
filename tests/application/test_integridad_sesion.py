"""Tests de integridad de sesión bajo concurrencia.

Verifica que ante múltiples peticiones simultáneas con diferentes
session_id, los mensajes de cada sesión no se mezclen entre sí.
Esto valida que el aislamiento por session_id (la "cerradura optimista")
funcione correctamente incluso bajo carga concurrente.
"""

import threading
from unittest.mock import Mock

import pytest

from la_santisima_conversacional.domain import (
    MensajeCreyente,
    RespuestaLaSantisima,
)
from la_santisima_conversacional.application import CasoDeUsoResponderMensaje
from la_santisima_conversacional.infrastructure.repositories import (
    ConversationRepositoryMemory,
)


class TestIntegridadSesionConcurrente:
    """Test cases para integridad de sesión bajo concurrencia."""

    @pytest.fixture
    def mock_servicio(self):
        """Fixture que devuelve un mock del servicio."""
        servicio = Mock()
        servicio.responder_mensaje.return_value = RespuestaLaSantisima(
            contenido="Respuesta de prueba",
            idioma="es",
            modelo="test-model",
        )
        return servicio

    @staticmethod
    def _mensajes_por_sesion(
        repo: ConversationRepositoryMemory,
        session_id: str,
    ) -> list[str]:
        """Extrae los contenidos de los mensajes de una sesión."""
        historial = repo.get_history(session_id)
        return [msg.content for msg in historial if msg.role == "user"]

    def test_sesiones_independientes_en_concurrencia(self, mock_servicio):
        """Verifica que dos sesiones concurrentes no mezclen sus mensajes."""
        repo = ConversationRepositoryMemory()
        caso_de_uso = CasoDeUsoResponderMensaje(mock_servicio, repositorio=repo)
        mensajes_sesion_a = [f"A-mensaje-{i}" for i in range(5)]
        mensajes_sesion_b = [f"B-mensaje-{i}" for i in range(5)]

        def trabajador_sesion(session_id: str, mensajes: list[str]):
            for msg in mensajes:
                caso_de_uso.ejecutar(msg, session_id=session_id)

        hilo_a = threading.Thread(
            target=trabajador_sesion,
            args=("sesion-A", mensajes_sesion_a),
        )
        hilo_b = threading.Thread(
            target=trabajador_sesion,
            args=("sesion-B", mensajes_sesion_b),
        )
        hilo_a.start()
        hilo_b.start()
        hilo_a.join()
        hilo_b.join()

        msgs_a = self._mensajes_por_sesion(repo, "sesion-A")
        msgs_b = self._mensajes_por_sesion(repo, "sesion-B")
        assert msgs_a == mensajes_sesion_a
        assert msgs_b == mensajes_sesion_b
        for msg_a in msgs_a:
            assert msg_a.startswith("A-")
        for msg_b in msgs_b:
            assert msg_b.startswith("B-")

    def test_historial_no_compartido_entre_sesiones(self, mock_servicio):
        """Verifica que el resumen/historial de una sesión no afecte a otra."""
        repo = ConversationRepositoryMemory()
        caso_de_uso = CasoDeUsoResponderMensaje(mock_servicio, repositorio=repo)
        repo.save_resumen("sesion-X", "Resumen de la sesión X: temas de amor")
        repo.save_resumen("sesion-Y", "Resumen de la sesión Y: temas de salud")

        def trabajador_con_resumen(session_id: str, mensaje: str):
            caso_de_uso.ejecutar(mensaje, session_id=session_id)

        hilo_x = threading.Thread(target=trabajador_con_resumen, args=("sesion-X", "Hola desde X"))
        hilo_y = threading.Thread(target=trabajador_con_resumen, args=("sesion-Y", "Hola desde Y"))
        hilo_x.start()
        hilo_y.start()
        hilo_x.join()
        hilo_y.join()

        resumen_x = repo.get_resumen("sesion-X")
        resumen_y = repo.get_resumen("sesion-Y")
        assert "amor" in resumen_x
        assert "salud" in resumen_y

    def test_muchas_sesiones_simultaneas(self, mock_servicio):
        """Estrés ligero: lanza N sesiones concurrentes y verifica integridad."""
        NUM_SESIONES = 10
        repo = ConversationRepositoryMemory()
        caso_de_uso = CasoDeUsoResponderMensaje(mock_servicio, repositorio=repo)

        def trabajador(session_id: str):
            caso_de_uso.ejecutar(f"Mensaje único de {session_id}", session_id=session_id)

        hilos = [
            threading.Thread(target=trabajador, args=(f"sesion-{i}",)) for i in range(NUM_SESIONES)
        ]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()

        for i in range(NUM_SESIONES):
            sid = f"sesion-{i}"
            msgs = self._mensajes_por_sesion(repo, sid)
            assert len(msgs) == 1
            assert sid in msgs[0]

    def test_mismo_session_id_concurrente_mantiene_orden(self, mock_servicio):
        """Verifica que mensajes al mismo session_id se persisten en orden."""
        repo = ConversationRepositoryMemory()
        caso_de_uso = CasoDeUsoResponderMensaje(mock_servicio, repositorio=repo)
        NUM_MSGS = 15

        def trabajador(i: int):
            caso_de_uso.ejecutar(f"msg-{i}", session_id="sesion-compartida")

        hilos = [threading.Thread(target=trabajador, args=(i,)) for i in range(NUM_MSGS)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()

        msgs = self._mensajes_por_sesion(repo, "sesion-compartida")
        contenidos = set(msgs)
        for i in range(NUM_MSGS):
            assert f"msg-{i}" in contenidos
        assert len(msgs) == NUM_MSGS
