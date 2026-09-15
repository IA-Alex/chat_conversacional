"""Reglas de negocio sobre el manejo de contexto conversacional.

Estas funciones eran, antes de este módulo, lógica duplicada (o exclusiva
de un solo adaptador): la ventana deslizante solo existía como expresión
CEL dentro de ``flow.json`` (inalcanzable para el adaptador de LangChain) y
la extracción del resumen persistente estaba copiada dentro de
``CrewAILaSantisimaAdapter``. Viven aquí porque son reglas de negocio sobre
qué contexto se le da al modelo, no detalles de qué motor de IA se use:
cualquier adaptador presente o futuro debe comportarse igual en esto.
"""

from typing import List, Optional

from .interfaces import Message


def aplicar_sliding_window(
    historial: Optional[List[Message]],
    ventana: int,
) -> List[Message]:
    """Recorta el historial a los últimos ``ventana`` mensajes.

    Minimiza tokens enviados al modelo sin descartar el historial completo
    del repositorio (que sigue disponible para otros usos, p. ej. auditoría).
    """
    if not historial:
        return []
    if ventana <= 0 or len(historial) <= ventana:
        return list(historial)
    return historial[-ventana:]


def extraer_resumen_persistente(historial: Optional[List[Message]]) -> str:
    """Extrae el resumen de memoria de largo plazo del historial, si existe.

    El resumen persistente se guarda como el mensaje ``system`` más reciente
    del historial (ver ``ConversationRepository.save_resumen``). Devuelve
    cadena vacía si no hay resumen previo (primera interacción de la sesión).
    """
    if not historial:
        return ""
    for mensaje in reversed(historial):
        if mensaje.role == "system":
            return mensaje.content
    return ""
