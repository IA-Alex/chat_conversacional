"""Funciones de validación para outputs de agentes.

Implementa validación programática de:
1. Respuestas de La Santísima Muerte (estructura, longitud, contenido)
2. Clasificaciones de intención y emoción
3. Resúmenes de memoria
4. Validación JSON de salidas de agentes
"""

from typing import Optional, Tuple


class ValidationError(Exception):
    """Excepción lanzada cuando falla la validación."""

    pass


def validar_respuesta_la_santisima(
    respuesta: object,
    max_longitud: int = 1000,
    min_longitud: int = 10,
    idiomas_permitidos: Tuple[str, ...] = ("es", "en", "fr", "de", "it", "pt"),
) -> Tuple[bool, Optional[str]]:
    """Valida una respuesta generada por La Santísima Muerte.

    Args:
        respuesta: Texto de la respuesta a validar.
        max_longitud: Máxima longitud permitida en caracteres.
        min_longitud: Mínima longitud permitida en caracteres.
        idiomas_permitidos: Tupla de códigos de idioma permitidos.

    Returns:
        Tupla (es_valido, mensaje_error).
        - es_valido: True si la respuesta es válida.
        - mensaje_error: Descripción del error si no es válida.
    """
    if not isinstance(respuesta, str):
        return False, f"Respuesta debe ser string, no {type(respuesta).__name__}"

    if len(respuesta.strip()) == 0:
        return False, "Respuesta no puede estar vacía"

    if len(respuesta) > max_longitud:
        return False, f"Respuesta demasiado larga ({len(respuesta)} > {max_longitud} caracteres)"

    if len(respuesta) < min_longitud:
        return False, f"Respuesta demasiado corta ({len(respuesta)} < {min_longitud} caracteres)"

    # Verificar caracteres no imprimibles (excepto espacios y saltos de línea)
    for i, char in enumerate(respuesta):
        if ord(char) < 32 and char not in ("\n", "\r", "\t"):
            return False, f"Carácter no imprimible en posición {i}: {repr(char)}"

    # Validación básica de contenido (no vacío después de limpiar espacios)
    contenido_limpio = respuesta.strip()
    if len(contenido_limpio) < 5:
        return False, "Contenido demasiado corto después de limpiar espacios"
    return True, None


def validar_clasificacion_intencion(
    clasificacion: object,
) -> Tuple[bool, Optional[str]]:
    """Valida una clasificación de intención y emoción.

    Args:
        clasificacion: Diccionario con estructura:
            {
                "intencion": "vacía" | "incompleta" | "válida",
                "emoción": str,
                "idioma": str (opcional),
                "confianza": float (opcional)
            }

    Returns:
        Tupla (es_valido, mensaje_error).
    """
    if not isinstance(clasificacion, dict):
        return False, f"Clasificación debe ser dict, no {type(clasificacion).__name__}"

    # Validar campos requeridos
    campos_requeridos = ["intencion", "emoción"]
    for campo in campos_requeridos:
        if campo not in clasificacion:
            return False, f"Falta campo requerido: {campo}"

    # Validar valores de intención. Sin tildes a propósito: coincide con los
    # tokens exactos que flow.json le pide al LLM que devuelva
    # ('vacia'/'incompleta'/'valida'). Antes esta lista usaba tildes
    # ('vacía'/'válida'), lo que hacía que la validación fallara siempre
    # contra la salida real del clasificador.
    intenciones_validas = ["vacia", "incompleta", "valida"]
    if clasificacion["intencion"] not in intenciones_validas:
        return (
            False,
            f"Intención inválida: {clasificacion['intencion']}. Debe ser una de: {intenciones_validas}",
        )

    # Validar emoción (debe ser string no vacío)
    emocion = clasificacion["emoción"]
    if not isinstance(emocion, str):
        return False, f"Emoción debe ser string, no {type(emocion).__name__}"

    if len(emocion.strip()) == 0:
        return False, "Emoción no puede estar vacía"

    # Validar idioma opcional
    if "idioma" in clasificacion and clasificacion["idioma"]:
        if not isinstance(clasificacion["idioma"], str):
            return False, f"Idioma debe ser string, no {type(clasificacion['idioma']).__name__}"

    # Validar confianza opcional
    if "confianza" in clasificacion and clasificacion["confianza"] is not None:
        confianza = clasificacion["confianza"]
        if not isinstance(confianza, (int, float)):
            return False, f"Confianza debe ser número, no {type(confianza).__name__}"
        if confianza < 0 or confianza > 1:
            return False, f"Confianza fuera de rango: {confianza}. Debe estar entre 0 y 1"

    return True, None


def validar_resumen_memoria(
    resumen: object, max_longitud: int = 500, min_longitud: int = 10
) -> Tuple[bool, Optional[str]]:
    """Valida un resumen de memoria persistente.

    Args:
        resumen: Texto del resumen a validar.
        max_longitud: Máxima longitud permitida en caracteres.
        min_longitud: Mínima longitud permitida en caracteres.

    Returns:
        Tupla (es_valido, mensaje_error).
    """
    if not isinstance(resumen, str):
        return False, f"Resumen debe ser string, no {type(resumen).__name__}"

    # Resumen puede estar vacío (para primera interacción)
    if len(resumen) == 0:
        return True, None

    if len(resumen) > max_longitud:
        return False, f"Resumen demasiado largo ({len(resumen)} > {max_longitud} caracteres)"

    if len(resumen) < min_longitud:
        return False, f"Resumen demasiado corto ({len(resumen)} < {min_longitud} caracteres)"

    # Verificar que no sea solo espacios
    contenido_limpio = resumen.strip()
    if len(contenido_limpio) < 5:
        return False, "Resumen demasiado corto después de limpiar espacios"

    return True, None
