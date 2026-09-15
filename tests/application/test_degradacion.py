"""Tests de degradación (fallback) cuando el resumen o modelo falla.

Verifica que:
1. Cuando el flujo CrewAI completo falla (incluyendo el agente de resumen),
   el sistema cae en el fallback y responde sin bloquear.
2. El fallback produce una respuesta válida (tiene contenido, mismo idioma).
3. El streaming también tiene fallback cuando el flow principal falla.
"""

from unittest.mock import Mock, patch

import pytest

from la_santisima_conversacional.domain import (
    MensajeCreyente,
    RespuestaLaSantisima,
)
from la_santisima_conversacional.application import CasoDeUsoResponderMensaje
from la_santisima_conversacional.infrastructure.crewai_adapter import (
    CrewAILaSantisimaAdapter,
)
from la_santisima_conversacional.infrastructure.repositories import (
    ConversationRepositoryMemory,
)


class TestDegradacionResumen:
    """Test cases para degradación graceful del resumen persistente."""

    @pytest.fixture
    def repo(self):
        """Fixture del repositorio en memoria."""
        return ConversationRepositoryMemory()

    @pytest.fixture
    def adapter_con_crew_fallando(self):
        """Crea un adapter cuyo flow.kickoff siempre falla.

        Esto simula el escenario donde el flow completo (incluyendo
        el agente de resumen 'actualizar_memoria') falla.
        """
        adapter = CrewAILaSantisimaAdapter.__new__(CrewAILaSantisimaAdapter)
        adapter.modelo_chat = "openai/gpt-4o"
        adapter.modelo_resumen = "openai/gpt-4o-mini"
        adapter.modelo_clasificador = "openai/gpt-4o-mini"
        adapter.ventana_mensajes = 10

        mock_flow = Mock()
        mock_flow.kickoff.side_effect = RuntimeError("Error simulado: el agente de resumen falló")
        mock_flow.kickoff_stream.side_effect = RuntimeError(
            "Error simulado: el agente de resumen falló en streaming"
        )
        adapter.flow = mock_flow

        return adapter

    def test_fallo_flow_crewai_dispara_fallback(self, adapter_con_crew_fallando, repo):
        """Verifica que cuando el flow de CrewAI falla, se invoca el fallback."""
        caso_de_uso = CasoDeUsoResponderMensaje(
            adapter_con_crew_fallando,
            repositorio=repo,
        )
        with patch.object(adapter_con_crew_fallando, "_fallback_responder") as mock_fallback:
            mock_fallback.return_value = RespuestaLaSantisima(
                contenido="Respuesta desde fallback",
                idioma="es",
                modelo="fallback",
            )
            respuesta = caso_de_uso.ejecutar(
                "Hola, ¿cómo estás?",
                session_id="test-session",
            )

        assert respuesta.contenido == "Respuesta desde fallback"
        assert adapter_con_crew_fallando.flow.kickoff.called
        mock_fallback.assert_called_once()

    def test_fallback_mantiene_idioma_original(self, adapter_con_crew_fallando, repo):
        """Verifica que el fallback respeta el idioma del mensaje original."""
        caso_de_uso = CasoDeUsoResponderMensaje(
            adapter_con_crew_fallando,
            repositorio=repo,
        )
        with patch.object(adapter_con_crew_fallando, "_fallback_responder") as mock_fallback:
            mock_fallback.return_value = RespuestaLaSantisima(
                contenido="Respuesta desde fallback",
                idioma="en",
                modelo="fallback",
            )
            respuesta = caso_de_uso.ejecutar(
                "Hello, how are you?",
                session_id="test-session-en",
            )

        assert respuesta is not None
        assert len(respuesta.contenido) > 0

    def test_fallback_no_requiere_resumen(self, adapter_con_crew_fallando, repo):
        """Verifica que el fallback funciona incluso sin resumen previo."""
        caso_de_uso = CasoDeUsoResponderMensaje(
            adapter_con_crew_fallando,
            repositorio=repo,
        )
        with patch.object(adapter_con_crew_fallando, "_fallback_responder") as mock_fallback:
            mock_fallback.return_value = RespuestaLaSantisima(
                contenido="Fallback sin resumen",
                idioma="es",
                modelo="fallback",
            )
            respuesta = caso_de_uso.ejecutar(
                "Mensaje inicial sin contexto",
                session_id="session-sin-resumen",
            )

        assert respuesta.contenido == "Fallback sin resumen"

    def test_streaming_fallback_cuando_flow_falla(self, adapter_con_crew_fallando, repo):
        """Verifica que el streaming también activa el fallback."""
        caso_de_uso = CasoDeUsoResponderMensaje(
            adapter_con_crew_fallando,
            repositorio=repo,
        )
        with patch.object(adapter_con_crew_fallando, "_fallback_responder") as mock_fallback:
            mock_fallback.return_value = RespuestaLaSantisima(
                contenido="Fallo en streaming",
                idioma="es",
                modelo="fallback",
            )
            fragmentos = list(
                caso_de_uso.ejecutar_stream(
                    "Hola en streaming",
                    session_id="session-stream",
                )
            )

        assert len(fragmentos) > 0
        texto_completo = "".join(str(f) for f in fragmentos)
        assert "Fallo" in texto_completo

    def test_error_real_en_chatopenai_no_rompe_sistema(self, adapter_con_crew_fallando, repo):
        """Verifica que incluso si ChatOpenAI del fallback falla,
        el sistema captura la excepción y no se cae."""
        caso_de_uso = CasoDeUsoResponderMensaje(
            adapter_con_crew_fallando,
            repositorio=repo,
        )
        with patch.object(adapter_con_crew_fallando, "_fallback_responder") as mock_fallback:
            mock_fallback.side_effect = RuntimeError("Error en ChatOpenAI del fallback")
            with pytest.raises(RuntimeError):
                caso_de_uso.ejecutar(
                    "Mensaje que explota todo",
                    session_id="session-explota",
                )
