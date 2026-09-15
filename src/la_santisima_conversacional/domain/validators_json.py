"""Funciones de validación JSON para outputs de agentes."""

import json
from typing import Dict, Any, Optional, Tuple


def validar_json_salida_agente(
    json_str: str, esquema_esperado: Optional[Dict[str, Any]] = None
) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """Valida que un string sea JSON válido y cumpla con un esquema opcional.

    Args:
        json_str: String que debería contener JSON.
        esquema_esperado: Esquema JSON Schema opcional para validación adicional.

    Returns:
        Tupla (es_valido, mensaje_error, datos_parseados).
    """
    try:
        datos = json.loads(json_str)
    except json.JSONDecodeError as e:
        return False, f"JSON inválido: {str(e)}", None

    # Validación básica de estructura (debe ser dict o list)
    if not isinstance(datos, (dict, list)):
        return False, f"JSON debe ser objeto o lista, no {type(datos).__name__}", datos

    # Validación de esquema opcional
    if esquema_esperado:
        # Validación básica de campos requeridos si el esquema los especifica
        if "required" in esquema_esperado and isinstance(datos, dict):
            campos_requeridos = esquema_esperado["required"]
            for campo in campos_requeridos:
                if campo not in datos:
                    return False, f"Falta campo requerido: {campo}", datos

        # Validación de tipos si el esquema los especifica
        if "properties" in esquema_esperado and isinstance(datos, dict):
            propiedades = esquema_esperado["properties"]
            for campo, tipo_esperado in propiedades.items():
                if campo in datos:
                    tipo_actual = type(datos[campo]).__name__
                    # Validación básica de tipo (simplificada)
                    if "type" in tipo_esperado:
                        tipo_esperado_str = tipo_esperado["type"]
                        # Mapeo de tipos Python a tipos JSON
                        tipo_mappings = {
                            "string": ["str"],
                            "integer": ["int"],
                            "number": ["int", "float"],
                            "boolean": ["bool"],
                            "array": ["list"],
                            "object": ["dict"],
                        }
                        if tipo_esperado_str in tipo_mappings:
                            tipos_validos = tipo_mappings[tipo_esperado_str]
                            if tipo_actual.lower() not in [t.lower() for t in tipos_validos]:
                                return (
                                    False,
                                    f"Campo '{campo}' tiene tipo incorrecto: {tipo_actual}, esperado: {tipo_esperado_str}",
                                    datos,
                                )

    return True, None, datos


def validar_esquema_clasificacion_intencion() -> Dict[str, Any]:
    """Retorna el esquema JSON esperado para clasificación de intención."""
    return {
        "type": "object",
        "required": ["intencion", "emoción"],
        "properties": {
            "intencion": {"type": "string", "enum": ["vacía", "incompleta", "válida"]},
            "emoción": {"type": "string"},
            "idioma": {"type": "string", "optional": True},
            "confianza": {"type": "number", "minimum": 0, "maximum": 1, "optional": True},
        },
    }
