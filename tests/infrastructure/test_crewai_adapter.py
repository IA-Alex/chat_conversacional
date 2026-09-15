"""Test de regresión: propagación de emoción en CrewAILaSantisimaAdapter.

Ejercita CrewAILaSantisimaAdapter completo (no flow.json aislado): mockea
únicamente `adapter.flow` (igual que test_crewai_adapter_resumen.py) para
verificar que la emoción detectada por `detectar_intencion` se propaga a
`RespuestaLaSantisima.emocion`, sin ningún enrutado especial por valor de
emoción — ver docs/compliance/gobernanza-ia.md §4 para la decisión de
retirar el enrutado de crisis que existía aquí.
"""

from unittest.mock import Mock

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

    def test_desesperacion_no_recibe_enrutado_especial(self, adapter):
        """'desesperacion' se propaga como cualquier otra emoción — no debe
        desviarse a ninguna respuesta fija (ver gobernanza-ia.md §4: el
        enrutado de crisis se retiró deliberadamente)."""
        adapter.flow = Mock()
        adapter.flow.kickoff.return_value = {
            "outputs": {
                "detectar_intencion": {
                    "raw": "Intencion: valida | Emocion: desesperacion"
                },
                "entregar_respuesta_principal": {"raw": "Respuesta generada por el LLM."},
            }
        }

        mensaje = MensajeCreyente("No sé cómo voy a pagar la renta", session_id="s9")
        respuesta = adapter.responder_mensaje(mensaje)

        assert respuesta.contenido == "Respuesta generada por el LLM."
        assert respuesta.emocion == "desesperacion"
