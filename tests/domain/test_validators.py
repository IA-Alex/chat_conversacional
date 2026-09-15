"""Tests para las funciones de validación de outputs."""

import json
import pytest

from la_santisima_conversacional.domain.validators import (
    validar_respuesta_la_santisima,
    validar_clasificacion_intencion,
    validar_resumen_memoria,
    ValidationError,
)
from la_santisima_conversacional.domain.validators_json import (
    validar_json_salida_agente,
    validar_esquema_clasificacion_intencion,
)


class TestValidacionRespuestaLaSantisima:
    """Tests para validar_respuesta_la_santisima."""

    def test_respuesta_valida(self):
        """Respuesta normal debe ser válida."""
        respuesta = (
            "Hola, mi hijo. Te escucho con amor y compasión. Cuéntame lo que llevas en tu corazón."
        )
        es_valido, error = validar_respuesta_la_santisima(respuesta)
        assert es_valido is True
        assert error is None

    def test_respuesta_vacia(self):
        """Respuesta vacía debe ser inválida."""
        respuesta = ""
        es_valido, error = validar_respuesta_la_santisima(respuesta)
        assert es_valido is False
        assert "no puede estar vacía" in error or "vacía" in error

    def test_respuesta_solo_espacios(self):
        """Respuesta con solo espacios debe ser inválida."""
        respuesta = "   \n  \t  "
        es_valido, error = validar_respuesta_la_santisima(respuesta)
        assert es_valido is False

    def test_respuesta_demasiado_corta(self):
        """Respuesta muy corta debe ser inválida."""
        respuesta = "Hola"
        es_valido, error = validar_respuesta_la_santisima(respuesta, min_longitud=20)
        assert es_valido is False
        assert "demasiado corta" in error

    def test_respuesta_demasiado_larga(self):
        """Respuesta muy larga debe ser inválida."""
        respuesta = "Hola " * 300  # ~1500 caracteres
        es_valido, error = validar_respuesta_la_santisima(respuesta, max_longitud=1000)
        assert es_valido is False
        assert "demasiado larga" in error


class TestValidacionClasificacionIntencion:
    """Tests para validar_clasificacion_intencion."""

    def test_clasificacion_valida_completa(self):
        """Clasificación completa y válida."""
        clasificacion = {
            "intencion": "valida",
            "emoción": "esperanzada",
            "idioma": "es",
            "confianza": 0.85,
        }
        es_valido, error = validar_clasificacion_intencion(clasificacion)
        assert es_valido is True
        assert error is None

    def test_clasificacion_valida_minima(self):
        """Clasificación mínima válida."""
        clasificacion = {"intencion": "incompleta", "emoción": "confusa"}
        es_valido, error = validar_clasificacion_intencion(clasificacion)
        assert es_valido is True
        assert error is None

    def test_clasificacion_falta_intencion(self):
        """Clasificación sin intención debe ser inválida."""
        clasificacion = {"emoción": "triste"}
        es_valido, error = validar_clasificacion_intencion(clasificacion)
        assert es_valido is False
        assert "intencion" in error

    def test_clasificacion_falta_emocion(self):
        """Clasificación sin emoción debe ser inválida."""
        clasificacion = {"intencion": "vacia"}
        es_valido, error = validar_clasificacion_intencion(clasificacion)
        assert es_valido is False
        assert "emoción" in error

    def test_clasificacion_intencion_invalida(self):
        """Clasificación con intención inválida."""
        clasificacion = {"intencion": "inexistente", "emoción": "feliz"}
        es_valido, error = validar_clasificacion_intencion(clasificacion)
        assert es_valido is False
        assert "Intención inválida" in error

    def test_clasificacion_emocion_vacia(self):
        """Clasificación con emoción vacía."""
        clasificacion = {"intencion": "valida", "emoción": ""}
        es_valido, error = validar_clasificacion_intencion(clasificacion)
        assert es_valido is False
        assert "no puede estar vacía" in error

    def test_clasificacion_confianza_invalida(self):
        """Clasificación con confianza fuera de rango."""
        clasificacion = {"intencion": "valida", "emoción": "neutral", "confianza": 1.5}
        es_valido, error = validar_clasificacion_intencion(clasificacion)
        assert es_valido is False
        assert "fuera de rango" in error

    def test_clasificacion_no_dict(self):
        """Clasificación que no es diccionario."""
        clasificacion = "no soy un dict"
        es_valido, error = validar_clasificacion_intencion(clasificacion)
        assert es_valido is False
        assert "debe ser dict" in error
