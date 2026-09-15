"""
Implementación concreta de la infraestructura usando crewAI

Adapta la interfaz de dominio a la implementación específica de crewAI.
Implementa sliding window, resumen persistente, y actualización de memoria asíncrona.
"""

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable, List, Optional, cast, Generator
from datetime import datetime

from crewai import Flow
from crewai.flow import Flow as FlowClass

if TYPE_CHECKING:
    # Solo para el chequeo de tipos: el import real de ChatOpenAI sigue
    # siendo perezoso (dentro de ``_fallback_responder``) para no forzar la
    # dependencia de langchain_openai en el resto de este adaptador, que
    # normalmente no la necesita (ver comentario en __init__). TYPE_CHECKING
    # es False en tiempo de ejecución, así que este import nunca se ejecuta
    # de verdad — solo existe para que mypy conozca el tipo de
    # ``self._fallback_llm``.
    from langchain_openai import ChatOpenAI

from ..domain import (
    MensajeCreyente,
    RespuestaLaSantisima,
    Message,
    ServicioLaSantisima,
    extraer_resumen_persistente,
    validar_o_usar_fallback,
)
from ..domain.validators import validar_clasificacion_intencion

logger = logging.getLogger(__name__)

# Nombres de método del flow cuyo output puede contener la respuesta final
# para el creyente, en orden de prioridad. Deben existir en flow.json.
_METODOS_RESPUESTA_FINAL = (
    "entregar_respuesta_corta",
    "entregar_respuesta_principal",
)
# Métodos cuyo output es el resumen de memoria persistente actualizado.
_METODOS_RESUMEN = ("persistir_resumen", "actualizar_memoria")
# Método cuyo output es la clasificación cruda de intención/emoción.
_METODO_CLASIFICACION = "detectar_intencion"


class CrewAILaSantisimaAdapter(ServicioLaSantisima):
    """Adaptador que implementa el servicio usando crewAI Flow con soporte
    de sliding window, memoria persistente y streaming.

    Implementa explícitamente el protocolo ServicioLaSantisima.
    """

    def __init__(
        self,
        flow_path: str,
        modelo_chat: str = "openai/google/gemma-4-31B-it-turbo",
        modelo_resumen: str = "openai/google/gemma-4-26B-A4B-it",
        modelo_clasificador: str = "openai/deepseek-ai/DeepSeek-V4-Flash-0731",
        ventana_mensajes: int = 10,
        llm_timeout_segundos: float = 20.0,
        llm_max_reintentos: int = 2,
    ):
        """
        Args:
            flow_path: Ruta al archivo flow.json (str o Path).
            modelo_chat: Modelo para generar respuestas.
            modelo_resumen: Modelo para resúmenes en background.
            modelo_clasificador: Modelo para clasificar intención/emoción.
            ventana_mensajes: Tamaño de la ventana deslizante de historial.
            llm_timeout_segundos: Timeout del cliente LLM de fallback. Antes
                no había timeout: una llamada colgada al proveedor bloqueaba
                la request indefinidamente en vez de degradar a error.
            llm_max_reintentos: Reintentos automáticos del cliente de fallback
                ante errores transitorios (rate limit, 5xx).
        """
        self.flow_path = Path(flow_path)
        self.modelo_chat = modelo_chat
        self.modelo_resumen = modelo_resumen
        self.modelo_clasificador = modelo_clasificador
        self.ventana_mensajes = ventana_mensajes
        self.llm_timeout_segundos = llm_timeout_segundos
        self.llm_max_reintentos = llm_max_reintentos
        # True si el flow declarativo no pudo cargarse y este adaptador
        # quedó operando permanentemente en modo degradado (solo fallback,
        # sin clasificación de intención ni memoria persistente). Antes
        # esto solo era detectable leyendo logs; un endpoint de salud
        # (ver presentation/http_api.py) lo expone para monitoreo/alertas.
        self.esta_degradado = False
        self.flow = self._configurar_flow()
        # Cliente LLM del fallback: se crea perezosamente y se reutiliza,
        # en vez de instanciar un ChatOpenAI nuevo (con su propio cliente
        # HTTP) en cada llamada a _fallback_responder.
        self._fallback_llm: Optional["ChatOpenAI"] = None

    def _configurar_flow(self) -> FlowClass:
        """Configura la instancia de Flow basada en el flow.json."""
        try:
            # Intentar cargar el flow desde el archivo JSON
            flow = Flow.from_file(self.flow_path)
            return flow
        except Exception:
            # Si falla la carga, crear un flow básico como fallback.
            # Se degrada permanentemente a _fallback_responder para esta
            # instancia: queda registrado con traceback para que sea
            # detectable en producción (antes solo se imprimía a stdout),
            # y ahora también expuesto vía self.esta_degradado.
            self.esta_degradado = True
            logger.error(
                "No se pudo cargar el flow desde %s. "
                "Este adaptador operará en modo degradado (solo fallback).",
                self.flow_path,
                exc_info=True,
            )
            return self._crear_flow_basico()

    def _crear_flow_basico(self) -> FlowClass:
        """Crea un flow básico como fallback cuando no se puede cargar el JSON."""
        # Esto es un fallback mínimo. En producción debería cargarse del JSON.
        flow = Flow(
            name="LaSantisimaFlowBasico",
            description="Flow básico de La Santísima Muerte como fallback",
        )

        # Configurar métodos básicos directamente
        # Nota: En la implementación real, esto se cargaría desde flow.json
        return flow

    @staticmethod
    def _formatear_historial(historial: Optional[List[Message]]) -> list[dict]:
        """Convierte el historial del dominio al formato que espera el flow state."""
        if not historial:
            return []
        return [{"role": msg.role, "content": msg.content} for msg in historial]

    def _build_inputs(
        self,
        mensaje: MensajeCreyente,
        historial: Optional[List[Message]] = None,
    ) -> dict:
        """Construye el diccionario de inputs para CrewAI.

        Los tipos coinciden con el schema definido en flow.json:
        - historial_completo: string (JSON serializado de array)
        - ventana_mensajes: integer
        - resumen_persistente: string
        """
        historial_dicts = self._formatear_historial(historial)
        resumen = extraer_resumen_persistente(historial)
        return {
            "mensaje_creyente": mensaje.contenido,
            "session_id": mensaje.session_id,
            "historial_completo": json.dumps(historial_dicts),
            "resumen_persistente": resumen,
            "ventana_mensajes": self.ventana_mensajes,
            "modelo_chat": self.modelo_chat,
            "modelo_resumen": self.modelo_resumen,
            "modelo_clasificador": self.modelo_clasificador,
            "timestamp": datetime.now().isoformat(),
        }

    def responder_mensaje(
        self,
        mensaje: MensajeCreyente,
        historial: Optional[List[Message]] = None,
        on_resumen_actualizado: Optional[Callable[[str], None]] = None,
    ) -> RespuestaLaSantisima:
        """Implementación concreta usando crewAI Flow con historial como contexto.

        Aplica sliding window sobre el historial para minimizar tokens,
        inyecta resumen persistente en el system prompt,
        y programa actualización de memoria en background.
        Si la actualización de memoria (resumen) falla, la respuesta principal
        no se ve afectada (fallback degradado).
        """
        inputs = self._build_inputs(mensaje, historial)
        emocion: Optional[str] = None
        try:
            # Ejecutar el flow y obtener el resultado.
            resultado = self.flow.kickoff(inputs=inputs)

            respuesta_final = self._extraer_respuesta_del_flow(resultado)
            clasificacion = self._extraer_clasificacion_del_flow(resultado)
            emocion = clasificacion.get("emoción") if clasificacion else None
            self._propagar_resumen_actualizado(resultado, on_resumen_actualizado)
            self._validar_clasificacion_del_flow(resultado)

        except Exception:
            logger.exception("Error ejecutando el flow para session_id=%s", mensaje.session_id)
            respuesta_final = self._fallback_responder(mensaje, historial).contenido
            emocion = None

        respuesta_final = self._validar_o_degradar(respuesta_final, mensaje, historial)

        return RespuestaLaSantisima(
            contenido=respuesta_final,
            idioma=mensaje.idioma,
            modelo=self.modelo_chat,
            emocion=emocion,
        )

    def responder_mensaje_stream(
        self,
        mensaje: MensajeCreyente,
        historial: Optional[List[Message]] = None,
        on_resumen_actualizado: Optional[Callable[[str], None]] = None,
    ) -> Generator[str, None, Optional[str]]:
        """Versión streaming de responder_mensaje usando crewAI Flow.

        Ideal para SSE: streamea la respuesta token a token mientras
        el usuario ya está viendo texto. La memoria se actualiza en
        background sin bloquear. El valor de retorno del generador (ver
        ``ServicioLaSantisima.responder_mensaje_stream``) lleva la emoción
        detectada, para exponerla al cliente sin mezclarla con los chunks
        de texto.
        """
        inputs = self._build_inputs(mensaje, historial)
        ya_emitio_algo = False
        try:
            for chunk in self.flow.kickoff_stream(inputs=inputs):
                ya_emitio_algo = True
                yield cast(str, chunk)

            self._propagar_resumen_actualizado(self.flow, on_resumen_actualizado)
            clasificacion = self._extraer_clasificacion_del_flow(self.flow)
            return clasificacion.get("emoción") if clasificacion else None

        except Exception:
            logger.exception("Error en streaming del flow para session_id=%s", mensaje.session_id)
            if ya_emitio_algo:
                # Ya se envió texto real de La Santísima Muerte al usuario. Anexar
                # aquí una respuesta de fallback completa mezclaría dos
                # respuestas distintas en un solo mensaje (corrupción visible
                # para el usuario). En su lugar, se corta el stream con un
                # aviso breve y explícito.
                yield "\n\n[La conexión se interrumpió. Por favor, intenta de nuevo.]"
                return None
            fallback_texto = self._fallback_responder(mensaje, historial).contenido
            for char in fallback_texto:
                yield char
            return None

    def _extraer_respuesta_del_flow(self, flow_result: object) -> str:
        """Extrae la respuesta final del resultado del flow.

        NOTA DE FIABILIDAD: la forma exacta en que crewAI Flow expone los
        outputs de sus métodos no está cubierta por pruebas de integración
        reales en este proyecto (los tests mockean el paquete `crewai`).
        Esta función intenta varias formas razonables y, si ninguna aplica,
        cae al último recurso registrando un warning para que la situación
        sea visible en logs de producción en vez de fallar en silencio.
        """
        if isinstance(flow_result, str):
            return flow_result

        if isinstance(flow_result, dict):
            posibles_keys = ["respuesta", "response", "output", "result", "contenido"]
            for key in posibles_keys:
                if key in flow_result:
                    return str(flow_result[key])

            if "outputs" in flow_result:
                outputs = flow_result["outputs"]
                for method_name in _METODOS_RESPUESTA_FINAL:
                    if method_name in outputs:
                        method_output = outputs[method_name]
                        if isinstance(method_output, dict) and "raw" in method_output:
                            return str(method_output["raw"])
                        return str(method_output)

        logger.warning(
            "No se pudo extraer la respuesta del flow con ninguna estrategia conocida; "
            "usando str(flow_result) como último recurso. tipo=%s",
            type(flow_result).__name__,
        )
        return str(flow_result)

    def _extraer_resumen_del_flow(self, flow_result: object) -> Optional[str]:
        """Extrae el resumen de memoria persistente actualizado por el flow, si existe.

        Busca en los outputs del flow el resultado de los métodos de
        actualización de memoria (ver `_METODOS_RESUMEN`). Devuelve None si
        no encuentra nada, para distinguir "no hay resumen nuevo" de
        "resumen vacío".
        """
        if isinstance(flow_result, dict):
            outputs = flow_result.get("outputs") if "outputs" in flow_result else flow_result
            if isinstance(outputs, dict):
                for method_name in _METODOS_RESUMEN:
                    if method_name in outputs:
                        method_output = outputs[method_name]
                        if isinstance(method_output, dict) and "raw" in method_output:
                            return str(method_output["raw"])
                        if method_output is not None:
                            return str(method_output)

        # Algunos runtimes de Flow exponen el estado final acumulado en un
        # atributo `.state` del propio objeto Flow (p. ej. tras agotar el
        # generador de kickoff_stream). Se comprueba de forma defensiva.
        state = getattr(flow_result, "state", None)
        if isinstance(state, dict):
            resumen = state.get("resumen_persistente")
            if resumen:
                return str(resumen)

        return None

    def _propagar_resumen_actualizado(
        self,
        flow_result: object,
        on_resumen_actualizado: Optional[Callable[[str], None]],
    ) -> None:
        """Invoca el callback de persistencia de resumen si hay uno nuevo.

        Antes, el resumen calculado por el flow (paso `actualizar_memoria` /
        `persistir_resumen`) se descartaba silenciosamente: nunca se
        guardaba en el repositorio, por lo que la "memoria de largo plazo"
        de la conversación nunca funcionaba realmente. Ver
        CasoDeUsoResponderMensaje, que pasa este callback.
        """
        if on_resumen_actualizado is None:
            return
        resumen = self._extraer_resumen_del_flow(flow_result)
        if not resumen:
            return
        try:
            on_resumen_actualizado(resumen)
        except Exception:
            # Persistir el resumen es una optimización de memoria, no debe
            # tumbar la respuesta principal si el repositorio falla.
            logger.exception("No se pudo persistir el resumen actualizado")

    def _validar_o_degradar(
        self,
        respuesta_final: str,
        mensaje: MensajeCreyente,
        historial: Optional[List[Message]],
    ) -> str:
        """Valida la respuesta antes de entregarla; si es inválida, usa el fallback.

        Antes, `validar_respuesta_la_santisima` se importaba pero nunca se
        invocaba: ninguna respuesta del LLM pasaba control de longitud,
        vacuidad o caracteres no imprimibles antes de llegar al usuario.
        La política de validación/degradación en sí (``validar_o_usar_fallback``)
        es compartida con ``LangChainAdapter`` para que ambos motores
        entreguen la misma garantía de calidad mínima al creyente.
        """
        respuesta_validada, _ = validar_o_usar_fallback(
            respuesta_final,
            lambda: self._fallback_responder(mensaje, historial).contenido,
        )
        return respuesta_validada

    def _extraer_clasificacion_del_flow(self, flow_result: object) -> Optional[dict]:
        """Extrae defensivamente la salida de `detectar_intencion` (intención + emoción).

        Acepta tanto el resultado de `kickoff()` (dict) como el propio
        objeto Flow tras agotar `kickoff_stream()` (con `.state`), igual
        que `_extraer_resumen_del_flow` — mismo patrón defensivo, porque
        ambos casos de uso (responder_mensaje y responder_mensaje_stream)
        necesitan esta clasificación. Devuelve None si no hay clasificación
        disponible o no se pudo parsear, para distinguirlo de una
        clasificación real con campos vacíos.
        """
        outputs = None
        if isinstance(flow_result, dict):
            outputs = flow_result.get("outputs") if "outputs" in flow_result else flow_result
        else:
            state = getattr(flow_result, "state", None)
            if isinstance(state, dict):
                outputs = state.get("outputs", state)

        if not isinstance(outputs, dict) or _METODO_CLASIFICACION not in outputs:
            return None
        method_output = outputs[_METODO_CLASIFICACION]
        texto = method_output.get("raw") if isinstance(method_output, dict) else method_output
        if not texto:
            return None

        partes = dict(p.strip().split(":", 1) for p in str(texto).split("|") if ":" in p)
        return {
            "intencion": partes.get("Intencion", "").strip().lower(),
            "emoción": partes.get("Emocion", "").strip().lower(),
        }

    def _validar_clasificacion_del_flow(self, flow_result: object) -> None:
        """Valida defensivamente la salida de `detectar_intencion`.

        La clasificación no bloquea la respuesta: solo se registra un
        warning si el LLM no siguió el formato esperado
        ("Intencion: <x> | Emocion: <y>"), para poder detectar deriva de
        prompt en producción en vez de descubrirlo por enrutamientos raros.
        """
        clasificacion = self._extraer_clasificacion_del_flow(flow_result)
        if clasificacion is None:
            return
        es_valida, error = validar_clasificacion_intencion(clasificacion)
        if not es_valida:
            logger.warning("Clasificación de intención con formato inesperado: %s", error)

    def _fallback_responder(
        self,
        mensaje: MensajeCreyente,
        historial: Optional[List[Message]] = None,
    ) -> RespuestaLaSantisima:
        """Mecanismo de fallback cuando el flow principal falla.

        Usa directamente el modelo de chat sin pasar por el flow CrewAI
        para no bloquear la conversación principal.
        """
        from langchain_openai import ChatOpenAI
        from langchain_core.output_parsers import StrOutputParser

        from .prompts import FALLBACK_PROMPT_TEMPLATE

        if self._fallback_llm is None:
            modelo = self.modelo_chat
            if "/" in modelo:
                modelo = modelo.split("/", 1)[1]
            self._fallback_llm = ChatOpenAI(
                model=modelo,
                timeout=self.llm_timeout_segundos,
                max_retries=self.llm_max_reintentos,
            )

        chain = FALLBACK_PROMPT_TEMPLATE | self._fallback_llm | StrOutputParser()
        contenido = chain.invoke({"mensaje": mensaje.contenido})
        return RespuestaLaSantisima(
            contenido=contenido,
            idioma=mensaje.idioma,
            modelo="fallback",
        )
