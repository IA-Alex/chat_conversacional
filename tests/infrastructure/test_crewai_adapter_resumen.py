"""Tests de regresión para dos bugs críticos de CrewAILaSantisimaAdapter:

1. El resumen de memoria persistente que calcula el flow se descartaba
   siempre; nunca llegaba a persistirse en el repositorio.
2. Si `kickoff_stream` fallaba después de haber emitido ya texto real al
   usuario, el adapter mezclaba ese texto parcial con una respuesta de
   fallback completa distinta, produciendo una respuesta híbrida corrupta.
"""

from unittest.mock import Mock

import pytest

from la_santisima_conversacional.domain import MensajeCreyente
from la_santisima_conversacional.infrastructure.crewai_adapter import (
    CrewAILaSantisimaAdapter,
)


@pytest.fixture
def adapter(tmp_path):
    flow_path = tmp_path / "flow.json"
    flow_path.write_text("{}")  # from_file fallará -> flow básico de fallback
    return CrewAILaSantisimaAdapter(flow_path=str(flow_path))


class TestPropagacionDeResumen:
    def test_resumen_se_persiste_via_callback(self, adapter):
        """El resumen calculado por 'persistir_resumen' debe llegar al callback."""
        adapter.flow = Mock()
        adapter.flow.kickoff.return_value = {
            "outputs": {
                "entregar_respuesta_principal": {"raw": "La paz sea contigo."},
                "persistir_resumen": {"raw": "El creyente pidió proteccion."},
            }
        }
        mensaje = MensajeCreyente("hola", session_id="s1")

        resumenes_guardados = []
        respuesta = adapter.responder_mensaje(
            mensaje,
            on_resumen_actualizado=resumenes_guardados.append,
        )

        assert respuesta.contenido == "La paz sea contigo."
        assert resumenes_guardados == ["El creyente pidió proteccion."]

    def test_sin_callback_no_falla(self, adapter):
        """Si no se pasa callback, la respuesta principal no se ve afectada."""
        adapter.flow = Mock()
        adapter.flow.kickoff.return_value = {
            "outputs": {
                "entregar_respuesta_principal": {"raw": "Esta es la respuesta principal."},
                "persistir_resumen": {"raw": "Resumen"},
            }
        }
        mensaje = MensajeCreyente("hola", session_id="s1")
        respuesta = adapter.responder_mensaje(mensaje)
        assert respuesta.contenido == "Esta es la respuesta principal."

    def test_error_en_callback_no_rompe_la_respuesta(self, adapter):
        """Persistir el resumen es una optimización; si falla, la respuesta
        principal debe seguir llegando al creyente."""
        adapter.flow = Mock()
        adapter.flow.kickoff.return_value = {
            "outputs": {
                "entregar_respuesta_principal": {"raw": "Esta es la respuesta principal."},
                "persistir_resumen": {"raw": "Resumen"},
            }
        }

        def callback_roto(_resumen):
            raise RuntimeError("repositorio caído")

        mensaje = MensajeCreyente("hola", session_id="s1")
        respuesta = adapter.responder_mensaje(mensaje, on_resumen_actualizado=callback_roto)
        assert respuesta.contenido == "Esta es la respuesta principal."

    def test_sin_resumen_en_outputs_no_invoca_callback(self, adapter):
        adapter.flow = Mock()
        adapter.flow.kickoff.return_value = {
            "outputs": {
                "entregar_respuesta_corta": {"raw": "Respuesta corta"},
            }
        }
        callback = Mock()
        mensaje = MensajeCreyente("", session_id="s1")
        adapter.responder_mensaje(mensaje, on_resumen_actualizado=callback)
        callback.assert_not_called()


class TestStreamingNoMezclaFallbackConRespuestaParcial:
    def test_fallo_a_mitad_de_stream_no_agrega_fallback_completo(self, adapter):
        """Si ya se emitió texto real y luego el stream falla, no se debe
        anexar una respuesta de fallback completa (regresión de bug crítico)."""

        def stream_que_falla(inputs=None):
            yield "La muerte "
            yield "te "
            raise ConnectionError("se cayó la conexión con el proveedor")

        adapter.flow = Mock()
        adapter.flow.kickoff_stream.side_effect = stream_que_falla

        mensaje = MensajeCreyente("hola", session_id="s1")
        chunks = list(adapter.responder_mensaje_stream(mensaje))

        texto = "".join(chunks)
        assert texto.startswith("La muerte te ")
        # No debe contener una segunda respuesta completa generada por
        # _fallback_responder (que en el fallback real invoca un LLM
        # distinto); solo debe llevar el aviso de corte explícito.
        assert texto.count("Eres La Santísima Muerte") == 0
        assert "interrumpi" in texto.lower() or "intenta de nuevo" in texto.lower()

    def test_fallo_antes_de_emitir_nada_usa_fallback_completo(self, adapter, monkeypatch):
        """Si el stream falla sin haber emitido nada aún, sí se puede caer
        de forma segura al fallback completo (no hay nada que mezclar)."""

        def stream_que_falla_de_inmediato(inputs=None):
            raise ConnectionError("nunca conectó")
            yield  # pragma: no cover - necesario para que sea generador

        adapter.flow = Mock()
        adapter.flow.kickoff_stream.side_effect = stream_que_falla_de_inmediato

        monkeypatch.setattr(
            adapter,
            "_fallback_responder",
            lambda mensaje, historial=None: Mock(contenido="respuesta de emergencia"),
        )

        mensaje = MensajeCreyente("hola", session_id="s1")
        chunks = list(adapter.responder_mensaje_stream(mensaje))
        assert "".join(chunks) == "respuesta de emergencia"
