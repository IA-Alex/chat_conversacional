"""Política de degradación validada, compartida por todos los adaptadores.

Antes de este módulo, cada adaptador de infraestructura decidía por su
cuenta si una respuesta del modelo era aceptable. En la práctica solo
``CrewAILaSantisimaAdapter`` lo hacía (``_validar_o_degradar``); el
adaptador de LangChain entregaba al creyente lo que fuera que el LLM
devolviera, sin control de longitud, vacuidad o caracteres no imprimibles.
Centralizar la política aquí garantiza que todo motor de IA presente o
futuro aplique el mismo criterio de calidad antes de responder.
"""

import logging
from typing import Callable, Tuple

from .validators import validar_respuesta_la_santisima

logger = logging.getLogger(__name__)


def validar_o_usar_fallback(
    respuesta: str,
    generar_fallback: Callable[[], str],
) -> Tuple[str, bool]:
    """Valida ``respuesta``; si no pasa, la reemplaza con ``generar_fallback()``.

    Args:
        respuesta: Respuesta candidata generada por el motor principal.
        generar_fallback: Callback perezoso que produce una respuesta de
            reemplazo. Solo se invoca si la validación falla, para no pagar
            el costo de una llamada adicional al LLM en el camino feliz.

    Returns:
        Tupla ``(respuesta_final, se_degrado)``. ``se_degrado`` es True si
        se tuvo que recurrir al fallback, para que el llamador pueda
        registrar el motivo con su propio contexto (session_id, etc.).
    """
    es_valida, error = validar_respuesta_la_santisima(respuesta)
    if es_valida:
        return respuesta, False

    logger.warning("Respuesta del motor principal no pasó validación (%s); usando fallback.", error)
    return generar_fallback(), True
