"""Tests para la política de respuesta de crisis emocional grave.

Verifica que un mensaje clasificado como 'desesperacion' nunca llega
al flujo devocional estándar en ambos motores (CrewAI y LangChain).
"""

from unittest.mock import Mock, patch
import pytest

from la_santisima_conversacional.domain import MensajeCreyente
from la_santisima_conversacional.domain.crisis import (
    generar_respuesta_crisis,
    ConfiguracionCrisis,
)


class TestPoliticaCrisis:
    """Tests para la función de política de crisis."""
    
    def test_generar_respuesta_crisis_con_defaults(self):
        """Verifica que genera respuesta con configuración por defecto."""
        mensaje = MensajeCreyente("No puedo más, quiero terminar con todo", session_id="s1")
        respuesta = generar_respuesta_crisis(mensaje)
        
        assert respuesta
        assert "ayuda profesional" in respuesta.lower()
        assert "línea de prevención" in respuesta.lower() or "prevención del suicidio" in respuesta.lower()
    
    def test_generar_respuesta_crisis_sin_personaje(self):
        """Verifica opción de romper personaje."""
        config = ConfiguracionCrisis(mantener_personaje=False)
        mensaje = MensajeCreyente("Estoy desesperado", session_id="s1")
        respuesta = generar_respuesta_crisis(mensaje, config)
        
        assert respuesta
        assert "Detectamos que estás pasando" in respuesta
    
    def test_generar_respuesta_crisis_con_cabecera_personalizada(self):
        """Verifica que se usa cabecera personalizada."""
        cabecera = "Reconozco la profundidad de tu dolor."
        config = ConfiguracionCrisis(cabecera_empatia=cabecera)
        mensaje = MensajeCreyente("Ayuda", session_id="s1")
        respuesta = generar_respuesta_crisis(mensaje, config)
        
        assert respuesta.startswith(cabecera) or cabecera in respuesta
    
    def test_generar_respuesta_crisis_con_texto_derivacion_personalizado(self):
        """Verifica texto de derivación personalizado."""
        derivacion = "Contacta al 911 o a un profesional de salud mental inmediatamente."
        config = ConfiguracionCrisis(texto_derivacion=derivacion)
        mensaje = MensajeCreyente("No aguanto más", session_id="s1")
        respuesta = generar_respuesta_crisis(mensaje, config)
        
        assert derivacion in respuesta


class TestIntegracionLangChain:
    """Tests de integración con adaptador de LangChain."""
    
    @patch("la_santisima_conversacional.infrastructure.langchain_adapter.generar_respuesta_crisis")
    def test_langchain_desesperacion_no_usa_cadena_principal(self, mock_crisis):
        """Verifica que desesperación no usa cadena principal."""
        from la_santisima_conversacional.infrastructure.langchain_adapter import LangChainAdapter
        
        # Mock de la respuesta de crisis
        mock_crisis.return_value = "Respuesta de crisis"
        
        # Crear adapter mockeado
        adapter = LangChainAdapter.__new__(LangChainAdapter)
        adapter.modelo_chat = "gpt-4o"
        adapter.modelo_resumen = "gpt-4o-mini"
        adapter.modelo_clasificador = "gpt-4o-mini"
        adapter.ventana_mensajes = 10
        
        # Configurar cadenas mock
        adapter._chain_clasificador = Mock(
            invoke=Mock(return_value="Intencion: valida | Emocion: desesperacion")
        )
        adapter._chain_principal = Mock()
        adapter._chain_vacia = Mock()
        adapter._chain_incompleta = Mock()
        adapter._chain_resumen = Mock()
        adapter._chain_fallback = Mock(invoke=Mock(return_value="Fallback"))
        
        mensaje = MensajeCreyente("No veo salida", session_id="s1")
        
        # Llamar al método (sin ejecutar realmente la cadena principal)
        with patch.object(adapter, '_actualizar_memoria'):
            respuesta = adapter.responder_mensaje(mensaje)
        
        # Verificar que NO se llamó a la cadena principal
        adapter._chain_principal.invoke.assert_not_called()
        
        # Verificar que sí se llamó a la función de crisis
        mock_crisis.assert_called_once()
        args, kwargs = mock_crisis.call_args
        assert args[0] == mensaje
        # El segundo argumento puede ser None o no estar presente
        if len(args) > 1:
            assert args[1] is None
        else:
            # Si no pasó segundo arg, kwargs debería estar vacío
            assert not kwargs

        # La emoción detectada ("desesperacion") debe propagarse a
        # RespuestaLaSantisima.emocion igual que en la rama devocional.
        assert respuesta.emocion == "desesperacion"


class TestIntegracionCrewAI:
    """Tests de integración con adaptador de CrewAI."""
    
    def test_flow_json_tiene_rama_crisis(self):
        """Verifica que flow.json tiene la rama de crisis."""
        import json
        from pathlib import Path
        
        flow_path = Path(__file__).resolve().parents[2] / "src" / "la_santisima_conversacional" / "infrastructure" / "flow.json"
        
        with open(flow_path) as f:
            flow = json.load(f)
        
        methods = flow.get("methods", {})
        
        # Verificar que existe el método enrutar_por_intencion con crisis_desesperacion
        assert "enrutar_por_intencion" in methods
        router = methods["enrutar_por_intencion"]
        assert "crisis_desesperacion" in router.get("emit", [])
        
        # Verificar que la expresión contiene desesperacion
        expr = router.get("do", {}).get("expr", "")
        assert "desesperacion" in expr.lower()
        
        # Verificar que existe el método responder_crisis_desesperacion
        assert "responder_crisis_desesperacion" in methods