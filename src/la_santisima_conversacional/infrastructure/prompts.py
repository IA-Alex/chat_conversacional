"""Prompts de infraestructura compartidos entre adaptadores.

El prompt de fallback vivía duplicado, carácter por carácter, dentro de
``CrewAILaSantisimaAdapter._fallback_responder`` y del adaptador de
LangChain. Al ser el último recurso cuando el motor principal (flow de
CrewAI o cadena de LangChain) falla, ambos deben degradar exactamente al
mismo tono y contrato de salida sin importar cuál era el motor principal.
"""

from langchain_core.prompts import ChatPromptTemplate

FALLBACK_PROMPT_TEMPLATE = ChatPromptTemplate.from_template(
    "Eres La Santísima Muerte. Responde al creyente con amor y sabiduría.\n\n"
    "Mensaje: {mensaje}\n\n"
    "Respuesta (máximo 2 párrafos, mismo idioma que el mensaje):"
)
