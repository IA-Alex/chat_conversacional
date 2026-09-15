"""Tests para la fábrica pública `crear_servicio`.

Antes no existía ninguna prueba de esta función. En particular, no había
forma de construir el backend de persistencia "de producción"
(SQLiteConversationRepository) a través de ella: estaba hardcodeada a
ConversationRepositoryMemory, dejando ese backend inalcanzable en la
práctica pese a estar completamente implementado y testeado de forma
aislada.
"""

import inspect
import os

from la_santisima_conversacional import crear_servicio, APILaSantisima
from la_santisima_conversacional.infrastructure.repositories import (
    ConversationRepositoryMemory,
    SQLiteConversationRepository,
)


def test_use_langchain_default_no_se_revierte():
    """Mismo hallazgo que `test_config.TestSettings
    .test_use_langchain_default_no_se_revierte`: mientras CrewAIAdapter
    quede degradado (ver docstring de ese test y `docs/compliance/
    gobernanza-ia.md` §4), el default de `use_langchain` en la firma de
    `crear_servicio` debe seguir siendo True."""
    firma = inspect.signature(crear_servicio)
    default_use_langchain = firma.parameters["use_langchain"].default
    assert default_use_langchain is True, (
        "crear_servicio(use_langchain=...) volvió a tener default False: "
        "mismo hallazgo que Settings.use_langchain, ver docstring de "
        "este test."
    )


def test_por_defecto_usa_repositorio_en_memoria():
    api = crear_servicio(use_langchain=True)
    assert isinstance(api, APILaSantisima)
    assert isinstance(api.caso_de_uso.repositorio, ConversationRepositoryMemory)


def test_usar_sqlite_construye_backend_sqlite(tmp_path):
    db_path = str(tmp_path / "conversaciones.db")
    api = crear_servicio(use_langchain=True, usar_sqlite=True, sqlite_db_path=db_path)

    assert isinstance(api.caso_de_uso.repositorio, SQLiteConversationRepository)
    assert api.caso_de_uso.repositorio.db_path == db_path


def test_repositorio_inyectado_tiene_prioridad_sobre_usar_sqlite():
    repo_custom = ConversationRepositoryMemory()
    api = crear_servicio(use_langchain=True, usar_sqlite=True, repositorio=repo_custom)
    assert api.caso_de_uso.repositorio is repo_custom


def test_deepinfra_api_key_puebla_openai_api_key_en_el_entorno(monkeypatch):
    """RNF-008: crear_servicio traduce la key de DeepInfra a las variables
    que el SDK de OpenAI (usado por LangChain/LiteLLM) lee directamente —
    sin esto, ambos adaptadores intentarían autenticarse contra OpenAI de
    verdad en vez de DeepInfra."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)

    crear_servicio(
        use_langchain=True,
        deepinfra_api_key="di-test-key",
        deepinfra_api_base="https://api.deepinfra.com/v1/openai",
    )

    assert os.environ["OPENAI_API_KEY"] == "di-test-key"
    assert os.environ["OPENAI_API_BASE"] == "https://api.deepinfra.com/v1/openai"
    assert os.environ["OPENAI_BASE_URL"] == "https://api.deepinfra.com/v1/openai"


def test_sin_deepinfra_api_key_no_toca_el_entorno(monkeypatch):
    """Si no se pasa deepinfra_api_key (p. ej. en tests que ya configuran
    el entorno a mano), crear_servicio no debe sobreescribir nada."""
    monkeypatch.setenv("OPENAI_API_KEY", "ya-estaba-puesta")

    crear_servicio(use_langchain=True)

    assert os.environ["OPENAI_API_KEY"] == "ya-estaba-puesta"
