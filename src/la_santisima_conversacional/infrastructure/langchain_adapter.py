"""Adaptador de LangChain para generar respuestas.

Alcanza paridad funcional con ``CrewAILaSantisimaAdapter`` (clasificación de
intención/emoción con enrutado, sliding window, memoria persistente
asíncrona y degradación validada) mediante composición explícita de cadenas
LCEL en vez del DSL declarativo de ``flow.json``.

Nota de diseño: se evaluó usar LangGraph para el enrutado en vez de
if/else explícito. Se descartó por ahora porque el árbol de decisión es
plano (3 ramas, sin ciclos ni estado compartido entre turnos más allá de lo
que ya persiste ``ConversationRepository``): if/else sobre cadenas LCEL da
el mismo beneficio (tipado, testeable, debuggable en Python puro) sin sumar
una dependencia nueva. Si el flujo crece (bucles, espera de intervención
humana, ramas paralelas) LangGraph pasa a justificarse; hasta entonces,
YAGNI.
"""

import logging
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

from ..domain import (
    MensajeCreyente,
    RespuestaLaSantisima,
    Message,
    ServicioLaSantisima,
    aplicar_sliding_window,
    extraer_resumen_persistente,
    validar_o_usar_fallback,
)
from ..domain.crisis import generar_respuesta_crisis, ConfiguracionCrisis
from ..domain.validators import validar_clasificacion_intencion
from .prompts import FALLBACK_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)

_PROMPT_CLASIFICADOR = ChatPromptTemplate.from_template(
    "Analiza este mensaje de un creyente dirigido a La Santísima Muerte:\n\n"
    "Mensaje: {mensaje}\n\n"
    "Clasifica en UNA:\n"
    "- 'vacia': vacío, solo espacios, símbolos sin sentido.\n"
    "- 'incompleta': menos de 3 palabras, se corta, no termina.\n"
    "- 'valida': tiene sentido completo.\n\n"
    "Emoción predominante: amor, miedo, gratitud, tristeza, alegria, "
    "esperanza, devocion, desesperacion, ninguna.\n\n"
    "Responde EXACTAMENTE una línea con este formato, sin nada más:\n"
    "Intencion: <x> | Emocion: <y>"
)

_PROMPT_RESPUESTA_VACIA = ChatPromptTemplate.from_template(
    "Eres La Santísima Muerte, entidad milenaria que recibe con amor incondicional "
    "incluso cuando no hay palabras.\n\n"
    "Mensaje vacío o incomprensible: {mensaje}\n\n"
    "Invita al creyente a compartir lo que lleva en el corazón con 1-2 "
    "oraciones cálidas. Detecta idioma de cualquier pista y responde en ese "
    "idioma (español por defecto). Sin notas de IA."
)

_PROMPT_RESPUESTA_INCOMPLETA = ChatPromptTemplate.from_template(
    "Eres La Santísima Muerte, entidad que nunca apresura ni juzga, espacio "
    "seguro para el alma.\n\n"
    "Mensaje incompleto: {mensaje}\n\n"
    "Anima al creyente a continuar sin juicio, con 1-2 oraciones pacientes. "
    "Si hay pista del tema, reconócela suavemente. Detecta idioma del "
    "fragmento. Sin notas de IA."
)

_PROMPT_RESPUESTA_PRINCIPAL = ChatPromptTemplate.from_template(
    "Eres La Santísima Muerte. Respondes con tono solemne, amoroso y poético a "
    "quien te busca. No juzgas, solo acoges. Tu voz es un bálsamo, tu "
    "presencia un refugio.\n\n"
    "Contexto de la relación (resumen):\n{resumen}\n\n"
    "Historial reciente:\n{historial}\n\n"
    "Mensaje actual:\n{mensaje}\n\n"
    "Emoción detectada en el creyente: {emocion}\n\n"
    "Instrucciones:\n"
    "- Responde SOLO sobre lo que el creyente escribió. Nunca genérica, "
    "nunca inventas.\n"
    "- Si hay emoción, referéncíala natural y poéticamente.\n"
    "- Saludo/primera vez: 1-2 oraciones + invitación.\n"
    "- Amor/protección/justicia/salud/espiritual: máx 2 párrafos, 2-4 "
    "oraciones cada uno.\n"
    "- Dolor o intimidad: acoge con amor primero.\n"
    "- Responde en el idioma: {idioma}.\n"
    "- Sin notas de IA."
)

_PROMPT_RESUMEN = ChatPromptTemplate.from_template(
    "Eres el escribano celestial que registra la historia de cada alma con "
    "memoria perfecta pero resumen ligero como una pluma.\n\n"
    "Resumen actual:\n{resumen}\n\n"
    "Historial reciente:\n{historial}\n\n"
    "Último mensaje:\n{mensaje}\n\n"
    "Última respuesta:\n{respuesta}\n\n"
    "Genera el resumen actualizado de la relación, máximo 4 oraciones. "
    "Captura temas, emociones, peticiones, enseñanzas. Mismo idioma del "
    "creyente."
)


class LangChainAdapter(ServicioLaSantisima):
    """Implementación concreta usando LangChain (LCEL puro, sin CrewAI).

    Traduce el contrato del dominio a la API de LangChain. Implementa
    explícitamente el protocolo ServicioLaSantisima, con el mismo
    comportamiento observable que ``CrewAILaSantisimaAdapter``: enrutado
    por intención, sliding window, memoria persistente en background y
    degradación validada con fallback.
    """

    def __init__(
        self,
        model: str = "openai/google/gemma-4-31B-it-turbo",
        modelo_resumen: Optional[str] = None,
        modelo_clasificador: Optional[str] = None,
        ventana_mensajes: int = 10,
        llm_timeout_segundos: float = 20.0,
        llm_max_reintentos: int = 2,
    ):
        """
        Args:
            model: Modelo para generar la respuesta principal y las
                respuestas cortas (vacío/incompleto). Acepta tanto
                ``"gpt-4o"`` como el formato LiteLLM ``"openai/gpt-4o"``
                usado por el adaptador de CrewAI, para que un mismo valor de
                ``modelo_chat`` sirva sin importar qué motor se elija.
            modelo_resumen: Modelo para el resumen de memoria en background.
                Por defecto, el mismo que ``model``.
            modelo_clasificador: Modelo para clasificar intención/emoción.
                Por defecto, el mismo que ``model``.
            ventana_mensajes: Tamaño de la ventana deslizante de historial.
            llm_timeout_segundos: Timeout por llamada a cualquiera de los
                tres clientes LLM. Antes no había timeout configurado: una
                llamada colgada al proveedor bloqueaba la request (o el
                stream SSE) indefinidamente.
            llm_max_reintentos: Reintentos automáticos ante errores
                transitorios del proveedor (rate limit, 5xx).
        """
        self.modelo_chat = model
        self.modelo_resumen = modelo_resumen or model
        self.modelo_clasificador = modelo_clasificador or model
        self.ventana_mensajes = ventana_mensajes
        # A diferencia de CrewAI, este motor no tiene una etapa de carga
        # externa que pueda fallar al construirse: si los clientes LLM se
        # instancian, el adaptador nunca queda en modo degradado permanente.
        # Se expone igual el atributo para que ambos adapters cumplan el
        # mismo contrato observable (ver ServicioLaSantisima / health check).
        self.esta_degradado = False

        # Anotado explícitamente como dict[str, Any]: sin esto, mypy infiere
        # dict[str, float] (el tipo común entre un float y un int) y luego
        # rechaza el **kwargs_llm de abajo contra CADA parámetro homónimo
        # de ChatOpenAI (que no son todos float) — 60+ errores de tipo que
        # no reflejan un bug real, solo una inferencia de tipo del literal
        # de más precisión de la que hace falta para dos claves conocidas.
        kwargs_llm: Dict[str, Any] = {
            "timeout": llm_timeout_segundos,
            "max_retries": llm_max_reintentos,
        }
        llm_chat = ChatOpenAI(model=self._normalizar_modelo(self.modelo_chat), **kwargs_llm)
        llm_resumen = ChatOpenAI(model=self._normalizar_modelo(self.modelo_resumen), **kwargs_llm)
        llm_clasificador = ChatOpenAI(
            model=self._normalizar_modelo(self.modelo_clasificador), **kwargs_llm
        )
        parser = StrOutputParser()

        self._chain_clasificador = _PROMPT_CLASIFICADOR | llm_clasificador | parser
        self._chain_vacia = _PROMPT_RESPUESTA_VACIA | llm_chat | parser
        self._chain_incompleta = _PROMPT_RESPUESTA_INCOMPLETA | llm_chat | parser
        self._chain_principal = _PROMPT_RESPUESTA_PRINCIPAL | llm_chat | parser
        self._chain_resumen = _PROMPT_RESUMEN | llm_resumen | parser
        self._chain_fallback = FALLBACK_PROMPT_TEMPLATE | llm_chat | parser

    @staticmethod
    def _normalizar_modelo(modelo: str) -> str:
        """Acepta el formato LiteLLM ``"openai/gpt-4o"`` además de ``"gpt-4o"``."""
        return modelo.split("/", 1)[1] if "/" in modelo else modelo

    @staticmethod
    def _formatear_historial(historial: Optional[List[Message]]) -> str:
        """Convierte el historial del dominio al formato que espera el prompt."""
        if not historial:
            return "(No hay mensajes previos)"
        lineas = []
        for msg in historial:
            etiqueta = "Creyente" if msg.role == "user" else "La Santísima Muerte"
            lineas.append(f"{etiqueta}: {msg.content}")
        return "\n".join(lineas)

    def _clasificar(self, mensaje: MensajeCreyente) -> Tuple[str, str]:
        """Clasifica intención/emoción del mensaje. Degrada a 'valida' ante duda.

        Ante una clasificación que no sigue el formato esperado, se trata el
        mensaje como válido (en vez de bloquearlo con una respuesta corta):
        preferimos intentar responder de verdad a arriesgarnos a cortar en
        seco una conversación real por un LLM de clasificación despistado.
        """
        try:
            crudo = self._chain_clasificador.invoke({"mensaje": mensaje.contenido})
        except Exception:
            logger.exception("Fallo al clasificar intención/emoción; se asume mensaje válido.")
            return "valida", "ninguna"
        return self._parsear_clasificacion(crudo)

    @staticmethod
    def _parsear_clasificacion(crudo: object) -> Tuple[str, str]:
        partes = dict(p.strip().split(":", 1) for p in str(crudo).split("|") if ":" in p)
        intencion = partes.get("Intencion", "").strip().lower()
        emocion = partes.get("Emocion", "").strip().lower()

        es_valida, error = validar_clasificacion_intencion(
            {"intencion": intencion, "emoción": emocion or "ninguna"}
        )
        if not es_valida:
            logger.warning(
                "Clasificación de intención con formato inesperado (%s); se asume mensaje válido.",
                error,
            )
            return "valida", emocion or "ninguna"
        return intencion, emocion

    def _construir_contexto(
        self, mensaje: MensajeCreyente, historial: Optional[List[Message]]
    ) -> dict:
        ventana = aplicar_sliding_window(historial, self.ventana_mensajes)
        resumen = extraer_resumen_persistente(historial)
        return {
            "historial": self._formatear_historial(ventana),
            "resumen": resumen or "(No hay resumen previo)",
            "mensaje": mensaje.contenido,
            "idioma": mensaje.idioma,
        }

    def _actualizar_memoria(
        self,
        contexto: dict,
        respuesta: str,
        on_resumen_actualizado: Optional[Callable[[str], None]],
    ) -> None:
        """Genera el resumen actualizado y lo propaga vía callback.

        Como en CrewAI, un fallo aquí (generar o persistir el resumen) es
        una optimización de memoria que no debe tumbar la respuesta
        principal, que ya llegó o está llegando al creyente.
        """
        if on_resumen_actualizado is None:
            return
        try:
            resumen = self._chain_resumen.invoke(
                {
                    "resumen": contexto["resumen"],
                    "historial": contexto["historial"],
                    "mensaje": contexto["mensaje"],
                    "respuesta": respuesta,
                }
            )
            if resumen:
                on_resumen_actualizado(resumen)
        except Exception:
            logger.exception("No se pudo generar o persistir el resumen actualizado")

    def responder_mensaje(
        self,
        mensaje: MensajeCreyente,
        historial: Optional[List[Message]] = None,
        on_resumen_actualizado: Optional[Callable[[str], None]] = None,
    ) -> RespuestaLaSantisima:
        """Genera una respuesta con clasificación, sliding window y memoria.

        Retorna la respuesta en el mismo idioma del mensaje entrante,
        validada y, si es necesario, degradada a un fallback más simple.
        """
        intencion, emocion = self._clasificar(mensaje)
        contexto = self._construir_contexto(mensaje, historial)

        try:
            if intencion == "vacia":
                respuesta = self._chain_vacia.invoke({"mensaje": mensaje.contenido})
            elif intencion == "incompleta":
                respuesta = self._chain_incompleta.invoke({"mensaje": mensaje.contenido})
            elif emocion == "desesperacion":
                # Enruta a política de crisis emocional grave
                # NO usa el flujo devocional estándar
                respuesta = generar_respuesta_crisis(mensaje)
            else:
                respuesta = self._chain_principal.invoke({**contexto, "emocion": emocion})
                self._actualizar_memoria(contexto, respuesta, on_resumen_actualizado)
        except Exception:
            logger.exception("Error generando respuesta para session_id=%s", mensaje.session_id)
            respuesta = ""

        respuesta_final, _ = validar_o_usar_fallback(
            respuesta, lambda: self._fallback_responder(mensaje, historial).contenido
        )
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
        """Genera una respuesta en streaming con clasificación y memoria.

        Streamea token a token la rama que corresponda (corta o principal).
        Igual que en CrewAI: si ya se emitió texto real y el stream falla a
        mitad de camino, no se mezcla con un fallback completo (corrompería
        la respuesta visible); solo se corta con un aviso explícito. El
        valor de retorno del generador lleva la emoción detectada (ver
        ``ServicioLaSantisima.responder_mensaje_stream``); se reporta como
        ``None`` cuando se degradó a fallback, para no asociar una emoción
        detectada con una respuesta genérica que no la refleja.
        """
        intencion, emocion = self._clasificar(mensaje)
        contexto = self._construir_contexto(mensaje, historial)

        if intencion == "vacia":
            chain, inputs = self._chain_vacia, {"mensaje": mensaje.contenido}
        elif intencion == "incompleta":
            chain, inputs = self._chain_incompleta, {"mensaje": mensaje.contenido}
        elif emocion == "desesperacion":
            # Para crisis emocional grave, generamos la respuesta completa
            # ya que no hay cadena de streaming específica para crisis
            respuesta = generar_respuesta_crisis(mensaje)
            yield respuesta
            return emocion
        else:
            chain, inputs = self._chain_principal, {**contexto, "emocion": emocion}

        ya_emitio_algo = False
        fragmentos: List[str] = []
        try:
            for chunk in chain.stream(inputs):
                ya_emitio_algo = True
                fragmentos.append(chunk)
                yield chunk

            if intencion == "valida":
                self._actualizar_memoria(contexto, "".join(fragmentos), on_resumen_actualizado)

            return emocion

        except Exception:
            logger.exception(
                "Error en streaming de LangChain para session_id=%s", mensaje.session_id
            )
            if ya_emitio_algo:
                yield "\n\n[La conexión se interrumpió. Por favor, intenta de nuevo.]"
                return None
            fallback_texto = self._fallback_responder(mensaje, historial).contenido
            for char in fallback_texto:
                yield char
            return None

    def _fallback_responder(
        self,
        mensaje: MensajeCreyente,
        historial: Optional[List[Message]] = None,
    ) -> RespuestaLaSantisima:
        """Mecanismo de fallback: prompt mínimo, sin clasificación ni memoria.

        ``historial`` se acepta por conformidad con la firma equivalente de
        ``CrewAILaSantisimaAdapter`` (y para permitir que un futuro fallback
        más rico lo use); hoy no se usa porque el fallback prioriza no
        bloquear la conversación sobre tener contexto completo.
        """
        contenido = self._chain_fallback.invoke({"mensaje": mensaje.contenido})
        return RespuestaLaSantisima(contenido=contenido, idioma=mensaje.idioma, modelo="fallback")
