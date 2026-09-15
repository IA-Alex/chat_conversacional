"""Inicializador del paquete de infraestructura."""

from .repositories import ConversationRepositoryMemory, SQLiteConversationRepository


def __getattr__(name: str) -> object:
    if name == "CrewAILaSantisimaAdapter":
        from .crewai_adapter import CrewAILaSantisimaAdapter

        return CrewAILaSantisimaAdapter
    if name == "LangChainAdapter":
        from .langchain_adapter import LangChainAdapter

        return LangChainAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# pylint: disable=undefined-all-variable
# Falso positivo: pylint no reconoce el patrón de carga perezosa vía
# __getattr__ a nivel de módulo (PEP 562, arriba). Ambos nombres sí
# resuelven en tiempo de ejecución — ver
# tests/infrastructure/test_lazy_imports.py, que importa vía el paquete
# (no el submódulo directo) para no dejar que esto se rompa en silencio.
__all__ = [
    "CrewAILaSantisimaAdapter",
    "LangChainAdapter",
    "ConversationRepositoryMemory",
    "SQLiteConversationRepository",
]
