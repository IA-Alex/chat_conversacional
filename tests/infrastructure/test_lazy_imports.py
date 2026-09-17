"""Verifica el patrón de carga perezosa de ``infrastructure/__init__.py``.

``CrewAILaSantisimaAdapter`` y ``LangChainAdapter`` no se importan a nivel
de módulo (evita forzar la dependencia de ``crewai``, opcional, solo por
importar el paquete) — se resuelven vía ``__getattr__`` (PEP 562). Pylint
no entiende ese patrón y marca ``__all__`` como si nombrara variables
inexistentes (``undefined-all-variable``, silenciado explícitamente en ese
archivo); este test es la prueba real de que sí resuelven, para que una
regresión en el patrón se note aquí y no en producción.
"""

from la_santisima_conversacional import infrastructure


def test_langchain_adapter_resuelve_via_getattr_del_paquete():
    from la_santisima_conversacional.infrastructure.langchain_adapter import (
        LangChainAdapter as _Directo,
    )

    assert infrastructure.LangChainAdapter is _Directo


def test_crewai_adapter_resuelve_via_getattr_del_paquete():
    # conftest.py registra un ``crewai`` falso en sys.modules antes de que
    # cualquier test importe nada, así que esto funciona incluso sin el
    # paquete real instalado (extra opcional, ver pyproject.toml).
    from la_santisima_conversacional.infrastructure.crewai_adapter import (
        CrewAILaSantisimaAdapter as _Directo,
    )

    assert infrastructure.CrewAILaSantisimaAdapter is _Directo


def test_nombre_inexistente_lanza_attribute_error():
    import pytest

    with pytest.raises(AttributeError):
        _ = infrastructure.EsteNombreNoExiste  # type: ignore[attr-defined]
