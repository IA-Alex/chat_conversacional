import sys
from pathlib import Path

# Add the src directory to sys.path so the package can be imported
_src = Path(__file__).resolve().parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

# Mock the crewai module before any test imports crewai_adapter
# This avoids the ModuleNotFoundError when crewai is not installed in tests
# that only need to interact with CrewAILaSantisimaAdapter via mocks.
import types

if "crewai" not in sys.modules:
    # Build a fake crewai package with all needed submodules and attributes
    _crewai = types.ModuleType("crewai")
    _crewai.__path__ = []
    _crewai.Agent = type("Agent", (), {})
    _crewai.Crew = type("Crew", (), {"__init__": lambda self, **kw: None})
    _crewai.Process = type("Process", (), {"sequential": "sequential"})
    sys.modules["crewai"] = _crewai

    # Fake crewai.process submodule
    _proc = types.ModuleType("crewai.process")
    _proc.Process = _crewai.Process
    sys.modules["crewai.process"] = _proc

    # Fake crewai.flow submodule
    _flow_mod = types.ModuleType("crewai.flow")

    # Create a Flow class with necessary methods
    class FakeFlow:
        def __init__(self, name="", description=""):
            self.name = name
            self.description = description

        @staticmethod
        def from_file(path):
            # Mock method that returns a FakeFlow instance
            return FakeFlow(name="MockedFlow", description="Mocked from file")

        def kickoff(self, inputs=None):
            # Mock kickoff that returns a simple result
            return "Mocked flow response"

        def kickoff_stream(self, inputs=None):
            # Mock streaming that yields chunks
            chunks = ["Mocked", " flow", " streaming", " response"]
            for chunk in chunks:
                yield chunk

    _flow_mod.Flow = FakeFlow
    # Add Flow as FlowClass for the import alias
    _flow_mod.FlowClass = FakeFlow
    _flow_mod.listen = lambda *a, **kw: (lambda f: f)
    _flow_mod.start = lambda *a, **kw: (lambda f: f)
    _flow_mod.router = lambda *a, **kw: (lambda f: f)
    _flow_mod.emit = lambda *a, **kw: (lambda f: f)
    sys.modules["crewai.flow"] = _flow_mod

    # Also add Flow to the main crewai module for from crewai import Flow
    _crewai.Flow = FakeFlow

    # Fake crewai.flow.flow submodule
    _flow_base = types.ModuleType("crewai.flow.flow")
    _flow_base.Flow = FakeFlow
    sys.modules["crewai.flow.flow"] = _flow_base

# Mock langchain_openai and langchain_core since they are not installed
# and are only used inside _fallback_responder in crewai_adapter.py
import types as _types

for _mod_name in (
    "langchain_openai",
    "langchain_core",
    "langchain_core.prompts",
    "langchain_core.output_parsers",
):
    if _mod_name not in sys.modules:
        _m = _types.ModuleType(_mod_name)
        sys.modules[_mod_name] = _m

# Add ChatOpenAI to langchain_openai mock
# The stub must accept **kwargs because langchain_adapter does ChatOpenAI(model=...)
if not hasattr(sys.modules.get("langchain_openai", _types.ModuleType("dummy")), "ChatOpenAI"):

    class _FakeChatOpenAI:
        def __init__(self, **kwargs):
            pass

        def invoke(self, *args, **kwargs):
            return type("FakeResult", (), {"content": ""})()

        def stream(self, *args, **kwargs):
            return iter([])

        def bind(self, **kwargs):
            # Espeja Runnable.bind() de LangChain: fija kwargs adicionales
            # (p. ej. max_tokens) y devuelve un runnable equivalente. Los
            # adaptadores lo usan para acotar la longitud de cada tipo de
            # respuesta (ver LangChainAdapter.__init__); el fake no necesita
            # aplicar los kwargs de verdad, solo seguir siendo invocable.
            return self

    sys.modules["langchain_openai"].ChatOpenAI = _FakeChatOpenAI

    class _FakeChatPromptTemplate:
        @classmethod
        def from_template(cls, template):
            return cls()

        def __ror__(self, other):
            return self

        def __or__(self, other):
            return self

        def invoke(self, *args, **kwargs):
            return "Respuesta simulada de La Santísima Muerte"

        def stream(self, *args, **kwargs):
            return iter([])

    sys.modules["langchain_core.prompts"].ChatPromptTemplate = _FakeChatPromptTemplate
    sys.modules["langchain_core.output_parsers"].StrOutputParser = type("StrOutputParser", (), {})
