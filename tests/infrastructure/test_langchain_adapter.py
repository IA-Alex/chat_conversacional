"""Tests para el adaptador de LangChain (LCEL puro, sin CrewAI).

Cubre la paridad funcional con CrewAILaSantisimaAdapter: enrutado por
intención/emoción, sliding window, memoria persistente vía callback y
degradación validada con fallback. Cada test construye el adaptador con
``__new__`` e inyecta cadenas Mock, en vez de instanciar el LLM real, para
no depender de un proveedor externo ni de las credenciales del entorno
(mismo patrón que ``tests/application/test_degradacion.py`` para CrewAI).
"""

from unittest.mock import Mock

import pytest

from la_santisima_conversacional.domain import MensajeCreyente, Message
from la_santisima_conversacional.infrastructure.langchain_adapter import LangChainAdapter


def _consumir_stream(generador):
    """Agota un generador de streaming y devuelve (chunks, valor_de_retorno).

    ``responder_mensaje_stream`` reporta la emoción detectada como el valor
    de retorno del generador (``StopIteration.value``), no como un chunk
    más — ver ``ServicioLaSantisima.responder_mensaje_stream``. ``list()``
    descarta ese valor, así que los tests que lo necesitan iteran a mano.
    """
    chunks = []
    valor_de_retorno = None
    while True:
        try:
            chunks.append(next(generador))
        except StopIteration as fin:
            valor_de_retorno = fin.value
            break
    return chunks, valor_de_retorno


def _crear_adapter(**chains) -> LangChainAdapter:
    """Construye un LangChainAdapter con cadenas Mock inyectadas.

    Evita __init__ (que instancia ChatOpenAI real) y solo setea los
    atributos que el adaptador realmente usa.
    """
    adapter = LangChainAdapter.__new__(LangChainAdapter)
    adapter.modelo_chat = "gpt-4o"
    adapter.modelo_resumen = "gpt-4o-mini"
    adapter.modelo_clasificador = "gpt-4o-mini"
    adapter.ventana_mensajes = 10

    adapter._chain_clasificador = chains.get(
        "clasificador", Mock(invoke=Mock(return_value="Intencion: valida | Emocion: gratitud"))
    )
    adapter._chain_vacia = chains.get("vacia", Mock())
    adapter._chain_incompleta = chains.get("incompleta", Mock())
    adapter._chain_principal = chains.get(
        "principal",
        Mock(invoke=Mock(return_value="La La Santísima Muerte responde con amor y calma.")),
    )
    adapter._chain_resumen = chains.get("resumen", Mock())
    adapter._chain_fallback = chains.get(
        "fallback",
        Mock(invoke=Mock(return_value="Respuesta de fallback con contenido suficiente.")),
    )
    return adapter


class TestClasificacionYEnrutado:
    def test_mensaje_valido_usa_cadena_principal(self):
        adapter = _crear_adapter()
        mensaje = MensajeCreyente("Ayúdame a encontrar paz", session_id="s1")

        respuesta = adapter.responder_mensaje(mensaje)

        adapter._chain_principal.invoke.assert_called_once()
        assert respuesta.contenido == "La La Santísima Muerte responde con amor y calma."
        assert respuesta.idioma == "es"
        assert respuesta.emocion == "gratitud"

    def test_mensaje_vacio_usa_respuesta_corta_y_no_actualiza_memoria(self):
        chain_vacia = Mock(invoke=Mock(return_value="Comparte lo que llevas en el corazón."))
        adapter = _crear_adapter(
            clasificador=Mock(invoke=Mock(return_value="Intencion: vacia | Emocion: ninguna")),
            vacia=chain_vacia,
        )
        mensaje = MensajeCreyente("   ", session_id="s1")
        callback = Mock()

        respuesta = adapter.responder_mensaje(mensaje, on_resumen_actualizado=callback)

        chain_vacia.invoke.assert_called_once()
        assert respuesta.contenido == "Comparte lo que llevas en el corazón."
        callback.assert_not_called()

    def test_mensaje_incompleto_usa_respuesta_corta(self):
        chain_incompleta = Mock(invoke=Mock(return_value="Tómate tu tiempo, aquí te escucho."))
        adapter = _crear_adapter(
            clasificador=Mock(
                invoke=Mock(return_value="Intencion: incompleta | Emocion: tristeza")
            ),
            incompleta=chain_incompleta,
        )
        mensaje = MensajeCreyente("ayuda con", session_id="s1")

        respuesta = adapter.responder_mensaje(mensaje)

        chain_incompleta.invoke.assert_called_once()
        assert respuesta.contenido == "Tómate tu tiempo, aquí te escucho."

    def test_clasificacion_con_formato_inesperado_degrada_a_valida(self):
        """Si el LLM clasificador no sigue el formato, no se bloquea la
        conversación con una respuesta corta: se trata como mensaje válido."""
        adapter = _crear_adapter(
            clasificador=Mock(invoke=Mock(return_value="no sigo el formato pedido"))
        )
        mensaje = MensajeCreyente("Quiero pedir protección para mi familia", session_id="s1")

        respuesta = adapter.responder_mensaje(mensaje)

        adapter._chain_principal.invoke.assert_called_once()
        assert respuesta.contenido == "La La Santísima Muerte responde con amor y calma."

    def test_fallo_del_clasificador_no_rompe_la_respuesta(self):
        adapter = _crear_adapter(
            clasificador=Mock(invoke=Mock(side_effect=RuntimeError("proveedor caído")))
        )
        mensaje = MensajeCreyente("Hola, La Santísima Muerte", session_id="s1")

        respuesta = adapter.responder_mensaje(mensaje)

        assert respuesta.contenido == "La La Santísima Muerte responde con amor y calma."


class TestSlidingWindowYResumen:
    def test_historial_se_recorta_a_la_ventana(self):
        adapter = _crear_adapter()
        adapter.ventana_mensajes = 2
        historial = [
            Message(role="user", content="msg1"),
            Message(role="assistant", content="msg2"),
            Message(role="user", content="msg3"),
        ]
        mensaje = MensajeCreyente("último mensaje", session_id="s1")

        adapter.responder_mensaje(mensaje, historial=historial)

        inputs_enviados = adapter._chain_principal.invoke.call_args.args[0]
        assert "msg1" not in inputs_enviados["historial"]
        assert "msg3" in inputs_enviados["historial"]

    def test_resumen_persistente_se_extrae_e_inyecta(self):
        adapter = _crear_adapter()
        historial = [
            Message(role="system", content="El creyente busca protección para su familia."),
            Message(role="user", content="hola"),
        ]
        mensaje = MensajeCreyente("otra vez yo", session_id="s1")

        adapter.responder_mensaje(mensaje, historial=historial)

        inputs_enviados = adapter._chain_principal.invoke.call_args.args[0]
        assert inputs_enviados["resumen"] == "El creyente busca protección para su familia."

    def test_memoria_se_persiste_via_callback(self):
        chain_resumen = Mock(invoke=Mock(return_value="Resumen actualizado de la relación."))
        adapter = _crear_adapter(resumen=chain_resumen)
        mensaje = MensajeCreyente("gracias por escucharme", session_id="s1")
        resumenes_guardados = []

        adapter.responder_mensaje(mensaje, on_resumen_actualizado=resumenes_guardados.append)

        chain_resumen.invoke.assert_called_once()
        assert resumenes_guardados == ["Resumen actualizado de la relación."]

    def test_error_en_callback_no_rompe_la_respuesta(self):
        adapter = _crear_adapter(resumen=Mock(invoke=Mock(return_value="Resumen.")))
        mensaje = MensajeCreyente("hola", session_id="s1")

        def callback_roto(_resumen):
            raise RuntimeError("repositorio caído")

        respuesta = adapter.responder_mensaje(mensaje, on_resumen_actualizado=callback_roto)

        assert respuesta.contenido == "La La Santísima Muerte responde con amor y calma."


class TestDegradacionValidada:
    def test_respuesta_vacia_del_llm_dispara_fallback(self):
        adapter = _crear_adapter(
            principal=Mock(invoke=Mock(return_value="   ")),
        )
        mensaje = MensajeCreyente("Cuéntame sobre el amor", session_id="s1")

        respuesta = adapter.responder_mensaje(mensaje)

        adapter._chain_fallback.invoke.assert_called_once()
        assert respuesta.contenido == "Respuesta de fallback con contenido suficiente."

    def test_error_al_generar_dispara_fallback(self):
        adapter = _crear_adapter(
            principal=Mock(invoke=Mock(side_effect=RuntimeError("proveedor caído"))),
        )
        mensaje = MensajeCreyente("Cuéntame sobre el amor", session_id="s1")

        respuesta = adapter.responder_mensaje(mensaje)

        adapter._chain_fallback.invoke.assert_called_once()
        assert respuesta.contenido == "Respuesta de fallback con contenido suficiente."


class TestStreaming:
    def test_streaming_mensaje_valido_actualiza_memoria_al_terminar(self):
        chain_resumen = Mock(invoke=Mock(return_value="Resumen del turno."))
        principal = Mock()
        principal.stream = Mock(return_value=iter(["La muerte ", "te acoge."]))
        adapter = _crear_adapter(principal=principal, resumen=chain_resumen)
        mensaje = MensajeCreyente("hola de nuevo", session_id="s1")
        resumenes = []

        chunks, emocion = _consumir_stream(
            adapter.responder_mensaje_stream(mensaje, on_resumen_actualizado=resumenes.append)
        )

        assert "".join(chunks) == "La muerte te acoge."
        assert resumenes == ["Resumen del turno."]
        assert emocion == "gratitud"

    def test_streaming_no_mezcla_fallback_con_respuesta_parcial(self):
        def stream_que_falla(_inputs):
            yield "La muerte "
            yield "te "
            raise ConnectionError("se cayó la conexión con el proveedor")

        principal = Mock()
        principal.stream = Mock(side_effect=stream_que_falla)
        adapter = _crear_adapter(principal=principal)
        mensaje = MensajeCreyente("hola", session_id="s1")

        chunks, emocion = _consumir_stream(adapter.responder_mensaje_stream(mensaje))
        texto = "".join(chunks)

        assert texto.startswith("La muerte te ")
        assert texto.count("Eres La Santísima Muerte") == 0
        assert "interrumpi" in texto.lower() or "intenta de nuevo" in texto.lower()
        assert emocion is None

    def test_streaming_fallo_antes_de_emitir_nada_usa_fallback_completo(self):
        def stream_que_falla_de_inmediato(_inputs):
            raise ConnectionError("nunca conectó")
            yield  # pragma: no cover - necesario para que sea generador

        principal = Mock()
        principal.stream = Mock(side_effect=stream_que_falla_de_inmediato)
        adapter = _crear_adapter(principal=principal)
        mensaje = MensajeCreyente("hola", session_id="s1")

        chunks, emocion = _consumir_stream(adapter.responder_mensaje_stream(mensaje))
        texto = "".join(chunks)

        assert texto == "Respuesta de fallback con contenido suficiente."
        assert emocion is None


def test_normalizar_modelo_acepta_formato_litellm():
    assert LangChainAdapter._normalizar_modelo("openai/gpt-4o") == "gpt-4o"
    assert LangChainAdapter._normalizar_modelo("gpt-4o") == "gpt-4o"
