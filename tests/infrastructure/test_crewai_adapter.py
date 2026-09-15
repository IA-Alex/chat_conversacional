"""Test de regresión: paridad de crisis en CrewAILaSantisimaAdapter.

Antes del fix, el nodo `responder_crisis_desesperacion` de flow.json
devolvía un string literal placeholder ("TODO: Implementar..."), que
CrewAILaSantisimaAdapter entregaba tal cual al creyente. Esto rompía la
paridad con LangChainAdapter, que sí invoca `generar_respuesta_crisis()`
(ver tests/domain/test_crisis.py::TestIntegracionLangChain).

Este test ejercita CrewAILaSantisimaAdapter completo (no flow.json aislado):
mockea únicamente `adapter.flow` (igual que test_crewai_adapter_resumen.py)
para simular que el router de flow.json tomó la rama 'crisis_desesperacion',
y verifica que la respuesta final es exactamente la de
`generar_respuesta_crisis()`, nunca el placeholder literal del flow.
"""

from unittest.mock import Mock, patch

import pytest

from src.la_santisima_conversacional.domain import MensajeCreyente
from src.la_santisima_conversacional.infrastructure.crewai_adapter import (
    CrewAILaSantisimaAdapter,
)


@pytest.fixture
def adapter(tmp_path):
    flow_path = tmp_path / "flow.json"
    flow_path.write_text("{}")  # from_file fallará -> flow básico de fallback
    return CrewAILaSantisimaAdapter(flow_path=str(flow_path))


class TestIntegracionCrewAICrisis:
    @patch("src.la_santisima_conversacional.infrastructure.crewai_adapter.generar_respuesta_crisis")
    def test_desesperacion_usa_generar_respuesta_crisis_no_placeholder(
        self, mock_crisis, adapter
    ):
        """Un mensaje que el router marca como crisis_desesperacion debe
        responderse con generar_respuesta_crisis(), nunca con el string
        literal declarado en el nodo de flow.json."""
        mock_crisis.return_value = "Respuesta real de contención y derivación."

        adapter.flow = Mock()
        adapter.flow.kickoff.return_value = {
            "outputs": {
                "detectar_intencion": {
                    "raw": "Intencion: valida | Emocion: desesperacion"
                },
                # Lo que produciría hoy el nodo placeholder de flow.json si
                # el adapter no lo interceptara:
                "responder_crisis_desesperacion": {
                    "raw": "TODO: Implementar llamada a política de crisis "
                    "(ver domain/crisis.py). Respuesta de contención breve "
                    "+ derivación a recursos de ayuda profesional."
                },
            }
        }

        mensaje = MensajeCreyente("No puedo más, quiero terminar con todo", session_id="s1")
        respuesta = adapter.responder_mensaje(mensaje)

        assert "TODO" not in respuesta.contenido
        assert respuesta.contenido == "Respuesta real de contención y derivación."
        assert respuesta.emocion == "desesperacion"
        mock_crisis.assert_called_once_with(mensaje)

    def test_desesperacion_sin_mock_no_contiene_todo(self, adapter):
        """Con la función de dominio real (sin mockear), la respuesta de
        crisis nunca debe contener el placeholder 'TODO'."""
        adapter.flow = Mock()
        adapter.flow.kickoff.return_value = {
            "outputs": {
                "detectar_intencion": {
                    "raw": "Intencion: valida | Emocion: desesperacion"
                },
                "responder_crisis_desesperacion": {
                    "raw": "TODO: Implementar llamada a política de crisis."
                },
            }
        }

        mensaje = MensajeCreyente("No veo salida a esto", session_id="s2")
        respuesta = adapter.responder_mensaje(mensaje)

        assert "TODO" not in respuesta.contenido
        assert "ayuda profesional" in respuesta.contenido.lower()

    @patch("src.la_santisima_conversacional.infrastructure.crewai_adapter.generar_respuesta_crisis")
    def test_desesperacion_en_streaming_usa_generar_respuesta_crisis(
        self, mock_crisis, adapter
    ):
        """La rama de crisis tampoco debe streamear el placeholder del
        nodo de flow.json; debe entregar la respuesta real de dominio."""
        mock_crisis.return_value = "Respuesta real de contención (stream)."

        adapter.flow = Mock()
        adapter.flow.state = {
            "outputs": {
                "responder_crisis_desesperacion": {
                    "raw": "TODO: placeholder que jamás debe llegar al creyente."
                }
            }
        }
        adapter.flow.kickoff_stream.return_value = iter(
            ["TODO: placeholder que jamás debe llegar al creyente."]
        )

        mensaje = MensajeCreyente("Ya no aguanto más", session_id="s3")
        generador = adapter.responder_mensaje_stream(mensaje)
        chunks = []
        emocion = None
        while True:
            try:
                chunks.append(next(generador))
            except StopIteration as fin:
                emocion = fin.value
                break
        texto = "".join(chunks)

        assert "TODO" not in texto
        assert texto == "Respuesta real de contención (stream)."
        assert emocion == "desesperacion"
        mock_crisis.assert_called_once_with(mensaje)


class TestEmocionCrewAI:
    """Verifica que la emoción detectada por `detectar_intencion` se
    propaga a `RespuestaLaSantisima.emocion` (no stream) y al valor de
    retorno del generador (streaming), en la rama que NO es crisis."""

    def test_emocion_se_propaga_en_respuesta_no_stream(self, adapter):
        adapter.flow = Mock()
        adapter.flow.kickoff.return_value = {
            "outputs": {
                "detectar_intencion": {"raw": "Intencion: valida | Emocion: gratitud"},
                "entregar_respuesta_principal": {"raw": "Gracias a ti, hijo mío."},
            }
        }

        mensaje = MensajeCreyente("Gracias por escucharme siempre", session_id="s6")
        respuesta = adapter.responder_mensaje(mensaje)

        assert respuesta.contenido == "Gracias a ti, hijo mío."
        assert respuesta.emocion == "gratitud"

    def test_emocion_se_propaga_en_streaming(self, adapter):
        adapter.flow = Mock()
        adapter.flow.state = {
            "outputs": {
                "detectar_intencion": {"raw": "Intencion: valida | Emocion: tristeza"},
            }
        }
        adapter.flow.kickoff_stream.return_value = iter(["Fragmento de respuesta."])

        mensaje = MensajeCreyente("Hoy me siento muy triste", session_id="s7")
        generador = adapter.responder_mensaje_stream(mensaje)
        chunks = []
        emocion = None
        while True:
            try:
                chunks.append(next(generador))
            except StopIteration as fin:
                emocion = fin.value
                break

        assert "".join(chunks) == "Fragmento de respuesta."
        assert emocion == "tristeza"

    def test_emocion_none_si_no_hay_clasificacion(self, adapter):
        """Si el flow no expone `detectar_intencion` (p. ej. flow degradado
        o mock incompleto), emocion debe ser None, no una cadena vacía."""
        adapter.flow = Mock()
        adapter.flow.kickoff.return_value = {
            "outputs": {
                "entregar_respuesta_principal": {"raw": "Respuesta sin clasificación."},
            }
        }

        mensaje = MensajeCreyente("Hola", session_id="s8")
        respuesta = adapter.responder_mensaje(mensaje)

        assert respuesta.emocion is None
