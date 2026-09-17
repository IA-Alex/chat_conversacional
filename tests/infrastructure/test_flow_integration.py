"""Tests de integración: validación del schema flow.json vs crewai_adapter."""

import json
from pathlib import Path

import pytest

from la_santisima_conversacional.domain import MensajeCreyente, Message
from la_santisima_conversacional.infrastructure.crewai_adapter import CrewAILaSantisimaAdapter

FLOW_JSON_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "src"
    / "la_santisima_conversacional"
    / "infrastructure"
    / "flow.json"
)


def test_flow_json_schema_tipos_coinciden_con_adapter():
    """Verifica que el schema declarado en flow.json es compatible
    con los tipos que realmente envía CrewAILaSantisimaAdapter.
    """
    # Cargar flow.json
    with open(FLOW_JSON_PATH) as f:
        flow = json.load(f)

    schema_props = flow["state"]["json_schema"]["properties"]

    # Verificar tipos esperados
    assert schema_props["mensaje_creyente"]["type"] == "string"
    assert schema_props["session_id"]["type"] == "string"
    assert (
        schema_props["historial_completo"]["type"] == "string"
    ), "Debe ser string porque el adapter serializa el historial como JSON string"
    assert schema_props["resumen_persistente"]["type"] == "string"
    assert schema_props["ventana_mensajes"]["type"] == "integer"
    assert schema_props["modelo_chat"]["type"] == "string"
    assert schema_props["modelo_resumen"]["type"] == "string"
    assert schema_props["modelo_clasificador"]["type"] == "string"
    assert schema_props["timestamp"]["type"] == "string"


def test_flow_json_listen_no_es_lista():
    """Verifica que listen sea string o lista de strings."""
    with open(FLOW_JSON_PATH) as f:
        flow = json.load(f)

    for name, method in flow["methods"].items():
        listen = method.get("listen")
        if listen is not None:
            if isinstance(listen, list):
                # Lista de strings está permitido
                for item in listen:
                    assert isinstance(item, str), (
                        f"Método {name!r} tiene listen={listen!r} con elemento "
                        f"{item!r} de tipo {type(item).__name__}. "
                        "La especificación CrewAI Flow solo permite string o lista de strings."
                    )
            else:
                # String único también está permitido
                assert isinstance(listen, str), (
                    f"Método {name!r} tiene listen={listen!r} de tipo {type(listen).__name__}. "
                    "La especificación CrewAI Flow solo permite string o lista de strings."
                )


def test_flow_json_referencias_validas():
    """Verifica que todos los listen apunten a métodos existentes o eventos emit."""
    with open(FLOW_JSON_PATH) as f:
        flow = json.load(f)

    methods = flow["methods"]
    all_method_names = set(methods.keys())
    all_emit_events = set()
    for name, m in methods.items():
        for e in m.get("emit") or []:
            all_emit_events.add(e)

    valid_targets = all_method_names | all_emit_events

    for name, method in methods.items():
        listen = method.get("listen")
        if listen:
            # listen puede ser string o lista de strings
            if isinstance(listen, list):
                for target in listen:
                    assert target in valid_targets, (
                        f"Método {name!r} escucha a {target!r} (de la lista {listen!r}) que no existe "
                        f"como método ni como evento emitido. "
                        f"Métodos: {sorted(all_method_names)}, Emits: {sorted(all_emit_events)}"
                    )
            else:
                assert listen in valid_targets, (
                    f"Método {name!r} escucha a {listen!r} que no existe "
                    f"como método ni como evento emitido. "
                    f"Métodos: {sorted(all_method_names)}, Emits: {sorted(all_emit_events)}"
                )


def test_build_inputs_coincide_con_flow_json_props():
    """Verifica que _build_inputs produce exactamente las propiedades del schema."""
    adapter = CrewAILaSantisimaAdapter(
        flow_path=str(FLOW_JSON_PATH),
        modelo_chat="openai/gpt-4o",
        modelo_resumen="openai/gpt-4o-mini",
        modelo_clasificador="openai/gpt-4o-mini",
        ventana_mensajes=10,
    )

    mensaje = MensajeCreyente("Hola, La Santísima Muerte", session_id="test-session")
    historial = [
        Message(role="user", content="Mensaje previo"),
        Message(role="assistant", content="Respuesta previa"),
    ]

    inputs = adapter._build_inputs(mensaje, historial)

    with open(FLOW_JSON_PATH) as f:
        flow = json.load(f)

    schema_props = set(flow["state"]["json_schema"]["properties"].keys())
    inputs_keys = set(inputs.keys())

    # Todas las keys de inputs deben estar en el schema
    missing_in_schema = inputs_keys - schema_props
    assert not missing_in_schema, f"Inputs que no están en schema: {missing_in_schema}"

    # Verificar tipos concretos
    assert isinstance(inputs["mensaje_creyente"], str)
    assert isinstance(inputs["session_id"], str)
    assert isinstance(
        inputs["historial_completo"], str
    ), "historial_completo debe ser string (JSON serializado)"
    assert isinstance(
        inputs["ventana_mensajes"], int
    ), f"ventana_mensajes debe ser int, got {type(inputs['ventana_mensajes']).__name__}"

    # Verificar que historial_completo sea JSON válido
    historial_parsed = json.loads(inputs["historial_completo"])
    assert isinstance(historial_parsed, list)
    assert len(historial_parsed) == 2


def test_build_inputs_sin_historial():
    """Verifica inputs sin historial previo."""
    adapter = CrewAILaSantisimaAdapter(
        flow_path=str(FLOW_JSON_PATH),
    )
    mensaje = MensajeCreyente("Test", session_id="s1")
    inputs = adapter._build_inputs(mensaje)

    assert inputs["session_id"] == "s1"
    assert json.loads(inputs["historial_completo"]) == []
    assert inputs["resumen_persistente"] == ""
    assert isinstance(inputs["ventana_mensajes"], int)


def test_flow_json_historial_completo_tipo_correcto():
    """Verifica que el schema de flow.json tiene historial_completo como string,
    coincidiendo con lo que crewai_adapter envía.
    """
    with open(FLOW_JSON_PATH) as f:
        flow = json.load(f)

    hc_schema = flow["state"]["json_schema"]["properties"]["historial_completo"]
    assert hc_schema["type"] == "string", (
        f"Se esperaba type=string para historial_completo, pero es {hc_schema['type']!r}. "
        "CrewAILaSantisimaAdapter._build_inputs envía json.dumps(...) que es un string."
    )
