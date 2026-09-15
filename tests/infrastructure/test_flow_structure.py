"""Validación estructural de flow.json.

Estas pruebas no ejecutan el flow (no hay credenciales de LLM en CI), pero
verifican la forma del documento contra las reglas del formato declarativo
de CrewAI Flow documentadas en AGENTS.md. Existen para blindar contra la
regresión de un bug real que hubo en este archivo: dos métodos
(`ejecutar_respuesta_vacia`, `ejecutar_respuesta_incompleta`) escuchaban un
evento con su propio nombre de método, algo que AGENTS.md prohíbe
explícitamente ("Methods must not listen to their own method name") y que
antes solo se detectaba corriendo el flow real contra CrewAI (los tests
unitarios mockean `crewai` por completo y no lo veían).
"""

import json
from pathlib import Path

import pytest

_FLOW_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "src"
    / "la_santisima_conversacional"
    / "infrastructure"
    / "flow.json"
)


@pytest.fixture(scope="module")
def flow() -> dict:
    with open(_FLOW_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def methods(flow: dict) -> dict:
    return flow["methods"]


def _listen_targets(method: dict) -> list[str]:
    listen = method.get("listen")
    if listen is None:
        return []
    return listen if isinstance(listen, list) else [listen]


def test_exactamente_un_metodo_de_entrada(methods: dict) -> None:
    entradas = [name for name, m in methods.items() if m.get("start")]
    assert len(entradas) == 1, f"Debe haber exactamente un start:true, hay: {entradas}"


def test_ningun_metodo_se_escucha_a_si_mismo(methods: dict) -> None:
    """Regresión del bug crítico: un método no puede listen a su propio nombre."""
    ofensores = [name for name, m in methods.items() if name in _listen_targets(m)]
    assert not ofensores, f"Métodos que se escuchan a sí mismos: {ofensores}"


def test_todas_las_referencias_listen_son_validas(methods: dict) -> None:
    """Todo `listen` debe apuntar a un método existente o a un evento emitido
    por algún router (`emit`)."""
    nombres_metodo = set(methods)
    eventos_emitidos = {
        evento for m in methods.values() if m.get("router") for evento in (m.get("emit") or [])
    }
    validos = nombres_metodo | eventos_emitidos

    huerfanos = {
        (name, destino)
        for name, m in methods.items()
        for destino in _listen_targets(m)
        if destino not in validos
    }
    assert not huerfanos, f"Referencias 'listen' sin destino válido: {huerfanos}"


def test_routers_puros_usan_expression(methods: dict) -> None:
    """Un router debería limitarse a decidir el evento, no generar contenido."""
    no_puros = [
        name
        for name, m in methods.items()
        if m.get("router") and m.get("do", {}).get("call") != "expression"
    ]
    assert not no_puros, f"Routers que no son 'call: expression': {no_puros}"


def test_expresiones_cel_no_usan_variables_no_documentadas(methods: dict) -> None:
    """Las únicas variables CEL disponibles son `state` y `outputs`
    (ver AGENTS.md). Cualquier otro identificador de nivel superior en una
    expresión (p. ej. la variable inexistente `listen`, usada antes en un
    router de este archivo) es casi con certeza un error."""
    permitidas = {"state", "outputs"}
    sospechosos = []
    for name, m in methods.items():
        do = m.get("do", {})
        if do.get("call") != "expression":
            continue
        expr = do.get("expr", "")
        # Heurística simple: variables tipo `foo.bar` o `foo(` al inicio de
        # una comparación; suficiente para detectar el caso conocido sin
        # implementar un parser CEL completo.
        for token in ("listen", "trigger", "event"):
            if token in expr and f"{token}." not in expr and f"outputs.{token}" not in expr:
                # Solo marcar si el token aparece como identificador aislado,
                # no como parte de otra palabra (p. ej. "eventos").
                import re

                if re.search(rf"\b{token}\b", expr):
                    sospechosos.append((name, token, expr))
    assert not sospechosos, f"Posibles variables CEL no soportadas: {sospechosos}"


def test_clasificacion_de_intencion_consistente(methods: dict) -> None:
    """El texto que se le pide al LLM que devuelva para 'incompleta' debe
    coincidir con el substring que el router realmente busca; de lo
    contrario mensajes incompletos pueden enrutarse como válidos."""
    detectar = methods["detectar_intencion"]["do"]["with"]
    router = methods["enrutar_por_intencion"]["do"]["expr"]

    for token in ("vacia", "incompleta"):
        assert token in detectar["goal"], f"goal no pide el token '{token}'"
        assert token in detectar["input"], f"input no pide el token '{token}'"
        assert f"'{token}'" in router, f"el router no busca '{token}'"
