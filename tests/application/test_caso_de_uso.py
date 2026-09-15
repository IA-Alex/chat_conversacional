"""Tests para los casos de uso de la capa de aplicación."""

from unittest.mock import Mock, patch
import pytest

from la_santisima_conversacional.domain import MensajeCreyente, RespuestaLaSantisima
from la_santisima_conversacional.application import CasoDeUsoResponderMensaje
from la_santisima_conversacional.infrastructure.repositories import (
    ConversationRepositoryMemory,
)


class TestCasoDeUsoResponderMensaje:
    """Test cases para el caso de uso principal."""

    @pytest.fixture
    def mock_servicio(self):
        """Fixture que devuelve un mock del servicio."""
        return Mock()

    @pytest.fixture
    def repo(self):
        """Fixture del repositorio en memoria."""
        return ConversationRepositoryMemory()

    def test_ejecutar_llama_al_servicio(self, mock_servicio, repo):
        """Verifica que el caso de uso delega correctamente al servicio."""
        # Configurar mock
        mensaje = "Hola mi reina"
        respuesta_esperada = "Hola mi hijo"
        mock_servicio.responder_mensaje.return_value = RespuestaLaSantisima(
            contenido=respuesta_esperada,
            idioma="es",
            modelo="test-model",
        )

        # Ejecutar
        caso_de_uso = CasoDeUsoResponderMensaje(mock_servicio, repositorio=repo)
        resultado = caso_de_uso.ejecutar(mensaje, session_id="test-session")

        # Verificar
        mock_servicio.responder_mensaje.assert_called_once()
        mensaje_args = mock_servicio.responder_mensaje.call_args[1]["mensaje"]
        assert isinstance(mensaje_args, MensajeCreyente)
        assert resultado.contenido == respuesta_esperada

    def test_ejecutar_pasa_correctamente_el_mensaje(self, mock_servicio, repo):
        """Verifica que el mensaje se pasa correctamente al servicio."""
        # Configurar mock
        mensaje = "Hello my queen"
        mock_servicio.responder_mensaje.return_value = RespuestaLaSantisima(
            contenido="Hello my child",
            idioma="en",
            modelo="test-model",
        )

        # Ejecutar
        caso_de_uso = CasoDeUsoResponderMensaje(mock_servicio, repositorio=repo)
        caso_de_uso.ejecutar(mensaje, session_id="test-session")

        # Verificar
        mensaje_pasado = mock_servicio.responder_mensaje.call_args[1]["mensaje"]
        assert mensaje_pasado.contenido == mensaje
        assert mensaje_pasado.idioma == "en"  # Verifica detección de idioma

    def test_ejecutar_persiste_resumen_via_callback(self, mock_servicio, repo):
        """Regresión: el resumen de memoria persistente que el servicio calcula
        debe terminar guardado en el repositorio. Antes se descartaba siempre
        porque nadie invocaba save_resumen."""
        mock_servicio.responder_mensaje.return_value = RespuestaLaSantisima(
            contenido="Respuesta completa y válida.",
            idioma="es",
            modelo="test-model",
        )

        def fake_responder_mensaje(mensaje, historial=None, on_resumen_actualizado=None):
            if on_resumen_actualizado is not None:
                on_resumen_actualizado("El creyente pidió protección para su familia.")
            return RespuestaLaSantisima(contenido="Respuesta completa y válida.", idioma="es", modelo="test-model")

        mock_servicio.responder_mensaje.side_effect = fake_responder_mensaje

        caso_de_uso = CasoDeUsoResponderMensaje(mock_servicio, repositorio=repo)
        caso_de_uso.ejecutar("Ayúdame La Santísima Muerte", session_id="s1")

        assert repo.get_resumen("s1") == "El creyente pidió protección para su familia."

    def test_ejecutar_stream_persiste_resumen_via_callback(self, mock_servicio, repo):
        """Misma regresión que arriba, para el camino de streaming."""

        def fake_stream(mensaje, historial=None, on_resumen_actualizado=None):
            if on_resumen_actualizado is not None:
                on_resumen_actualizado("Resumen actualizado en streaming.")
            yield "Hola "
            yield "creyente."

        mock_servicio.responder_mensaje_stream.side_effect = fake_stream

        caso_de_uso = CasoDeUsoResponderMensaje(mock_servicio, repositorio=repo)
        chunks = list(caso_de_uso.ejecutar_stream("Hola", session_id="s2"))

        assert "".join(chunks) == "Hola creyente."
        assert repo.get_resumen("s2") == "Resumen actualizado en streaming."
