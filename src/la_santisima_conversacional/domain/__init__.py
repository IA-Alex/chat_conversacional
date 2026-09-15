"""
Dominio de la aplicación La Santísima Muerte Conversacional

Contiene las entidades, objetos de valor, reglas de negocio centrales
y los contratos (interfaces) que definen los puertos de la arquitectura.
"""

from .interfaces import (
    Message,
    ConversationRepository,
    ServicioLaSantisima,
    LLMService,
)
from .conversacion import aplicar_sliding_window, extraer_resumen_persistente
from .degradacion import validar_o_usar_fallback

import re
from typing import Optional

# Palabras clave por idioma para detección básica.
# Se evalúa el peso de coincidencias con palabras completas (word boundaries).
_IDIOMAS: dict[str, set[str]] = {
    "en": {
        "hello",
        "hi",
        "thanks",
        "thank",
        "please",
        "help",
        "bless",
        "queen",
        "king",
        "love",
        "pray",
        "god",
        "jesus",
        "mary",
    },
    "pt": {
        "olá",
        "ola",
        "obrigado",
        "obrigada",
        "por favor",
        "ajuda",
        "deus",
        "amor",
        "bênção",
        "bencao",
        "senhor",
    },
    "fr": {
        "bonjour",
        "merci",
        "s'il vous plaît",
        "aide",
        "dieu",
        "amour",
        "bénédiction",
        "benediction",
    },
}


class MensajeDemasiadoLargoError(ValueError):
    """El contenido del mensaje excede la longitud máxima permitida.

    Un mensaje vacío o solo-espacios NO se rechaza aquí: es un caso de
    negocio válido y esperado (ver ``flow.json`` / ``_clasificar`` en los
    adapters, rama "vacia"), que La Santísima Muerte responde invitando al
    creyente a compartir lo que lleva en el corazón. Rechazarlo en el
    dominio rompería ese flujo intencional.
    """


class MensajeCreyente:
    """Representa un mensaje enviado por un creyente a La Santísima Muerte.

    Antes solo se validaba la *salida* del LLM (``validar_respuesta_...``);
    la entrada del usuario se aceptaba tal cual, sin límite de tamaño ni
    filtrado de caracteres de control, lo que dejaba pasar payloads
    arbitrariamente grandes (costo/DoS hacia el proveedor del LLM) y
    caracteres de control ocultos en el prompt. La validación ocurre aquí,
    en el constructor de la entidad de dominio, para que ningún camino
    (API HTTP, uso programático directo) pueda saltársela.
    """

    LONGITUD_MAXIMA = 4000

    def __init__(self, contenido: str, session_id: str = "default"):
        contenido_normalizado = self._validar_y_normalizar(contenido)
        self.contenido = contenido_normalizado
        self.session_id = session_id
        self.idioma = self._detectar_idioma()

    @classmethod
    def _validar_y_normalizar(cls, contenido: str) -> str:
        if not isinstance(contenido, str):
            raise TypeError(f"contenido debe ser str, no {type(contenido).__name__}")
        if len(contenido) > cls.LONGITUD_MAXIMA:
            raise MensajeDemasiadoLargoError(
                f"Mensaje demasiado largo ({len(contenido)} > {cls.LONGITUD_MAXIMA} caracteres)."
            )
        # Elimina caracteres de control (excepto \n, \r, \t) antes de que
        # lleguen a ningún prompt: no aportan significado y algunos se usan
        # en técnicas de prompt injection para ocultar instrucciones.
        return "".join(c for c in contenido if c in ("\n", "\r", "\t") or ord(c) >= 32)

    @staticmethod
    def _coincidencias(texto: str, palabras: set[str]) -> int:
        """Cuenta cuántas palabras/frases del set aparecen en el texto.

        Las entradas de una sola palabra deben aparecer como palabra
        completa (word boundary, vía tokenización). Las entradas de varias
        palabras (p. ej. "por favor", "s'il vous plaît") no pueden pasar
        por ese tokenizador -lo divide en palabras sueltas y nunca
        reconstruye la frase-, así que se comprueban como substring directo
        sobre el texto normalizado. Antes todas las entradas multi-palabra
        del diccionario de idiomas eran, en la práctica, inalcanzables.
        """
        texto_lower = texto.lower()
        tokens = set(re.findall(r"[a-záéíóúàâêôãõçüñ]+", texto_lower))
        total = 0
        for palabra in palabras:
            if " " in palabra or "'" in palabra:
                if palabra in texto_lower:
                    total += 1
            elif palabra in tokens:
                total += 1
        return total

    def _detectar_idioma(self) -> str:
        """Detecta el idioma principal del mensaje usando coincidencia ponderada."""
        if not self.contenido.strip():
            return "es"
        texto = self.contenido.lower()
        puntuacion: dict[str, int] = {}
        for idioma, palabras in _IDIOMAS.items():
            puntuacion[idioma] = self._coincidencias(texto, palabras)
        # Si inglés tiene más coincidencias que español, elegimos inglés;
        # por defecto español. Esto evita falsos positivos con palabras
        # comunes como "love" que aparecen en ambos.
        if puntuacion.get("en", 0) > puntuacion.get("es", 0):
            return "en"
        if puntuacion.get("pt", 0) > 0:
            return "pt"
        if puntuacion.get("fr", 0) > 0:
            return "fr"
        return "es"


class RespuestaLaSantisima:
    """Representa una respuesta generada por La Santísima Muerte."""

    def __init__(
        self,
        contenido: str,
        idioma: str,
        modelo: Optional[str] = None,
        emocion: Optional[str] = None,
    ):
        self.contenido = contenido
        self.idioma = idioma
        self.modelo = modelo
        self.emocion = emocion


__all__ = [
    "Message",
    "ConversationRepository",
    "ServicioLaSantisima",
    "LLMService",
    "MensajeCreyente",
    "MensajeDemasiadoLargoError",
    "RespuestaLaSantisima",
    "aplicar_sliding_window",
    "extraer_resumen_persistente",
    "validar_o_usar_fallback",
]
