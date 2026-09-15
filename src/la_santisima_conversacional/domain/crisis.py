"""Política de respuesta para crisis emocional grave.

Implementa el enrutado para mensajes clasificados como de desesperación,
sin decidir el contenido exacto de derivación (eso corresponde al responsable
del producto según gobernanza-ia.md §4).

Contiene:
- ``generar_respuesta_crisis()``: función de política que recibe el mensaje
  y devuelve una respuesta de contención breve + derivación configurable.
- El contenido de derivación (tono, líneas de ayuda) queda como parámetro
  inyectable para que el responsable del producto pueda definirlo sin
  tocar código.
"""

from typing import Optional
from dataclasses import dataclass

from . import MensajeCreyente


@dataclass
class ConfiguracionCrisis:
    """Configuración inyectable para la respuesta de crisis.
    
    Permite que el responsable del producto defina el tono y contenido
    sin necesidad de modificar el código Python, según lo requerido por
    gobernanza-ia.md §4.
    """
    # TODO: contenido pendiente de definición por el responsable del producto
    # Debe decidir si rompe personaje o no, y qué líneas de ayuda incluir.
    texto_derivacion: str = (
        "Por favor, busca ayuda profesional inmediata. Llama a la línea "
        "de prevención del suicidio en tu país o acude a un centro de "
        "salud mental. No estás solo/a."
    )
    
    # Si True, mantiene el tono devocional de La Santísima Muerte
    # Si False, rompe personaje y habla directamente como sistema de IA
    mantener_personaje: bool = True
    
    # Cabecera antes de la derivación (opcional)
    cabecera_empatia: str = (
        "Escucho tu dolor profundo y reconozco la carga que llevas."
    )


def generar_respuesta_crisis(
    mensaje: MensajeCreyente,
    config: Optional[ConfiguracionCrisis] = None,
) -> str:
    """Genera respuesta para mensajes clasificados como crisis emocional grave.
    
    Implementa la política de enrutado requerida por la auditoría:
    - NO envía el mensaje al flujo devocional estándar
    - Devuelve respuesta de contención breve + derivación a recursos de ayuda
    - El contenido exacto es configurable/inyectable
    
    Args:
        mensaje: Mensaje del creyente clasificado como desesperación.
        config: Configuración opcional de contenido y tono. Si None, usa defaults.
        
    Returns:
        Respuesta apropiada para crisis emocional grave.
    """
    config = config or ConfiguracionCrisis()
    
    if config.mantener_personaje:
        # Mantiene el personaje de La Santísima Muerte
        base = f"{config.cabecera_empatia} Te abrazo con mi manto de luz.\n\n"
    else:
        # Rompe personaje (modo sistema transparente)
        base = f"Detectamos que estás pasando por un momento muy difícil. {config.cabecera_empatia}\n\n"
    
    return base + config.texto_derivacion