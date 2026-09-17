"""Tests para las entidades del dominio."""

import pytest

from la_santisima_conversacional.domain import MensajeCreyente


class TestMensajeCreyente:
    """Test cases para la entidad MensajeCreyente."""

    def test_creacion_mensaje_ingles(self):
        """Verifica que se detecta correctamente el idioma inglés."""
        mensaje = MensajeCreyente("Hello my queen")
        assert mensaje.idioma == "en"

    def test_creacion_mensaje_espanol(self):
        """Verifica que el idioma por defecto es español."""
        mensaje = MensajeCreyente("Hola mi reina")
        assert mensaje.idioma == "es"

    def test_contenido_mensaje(self):
        """Verifica que el contenido se almacena correctamente."""
        texto = "Hello my queen"
        mensaje = MensajeCreyente(texto)
        assert mensaje.contenido == texto

    def test_deteccion_idioma_portugues(self):
        """Verifica detección de portugués."""
        mensaje = MensajeCreyente("Obrigado Senhor pela bênção")
        assert mensaje.idioma == "pt"

    def test_deteccion_idioma_frances(self):
        """Verifica detección de francés."""
        mensaje = MensajeCreyente("Merci pour votre aide Dieu")
        assert mensaje.idioma == "fr"

    def test_deteccion_idioma_vacio_default_espanol(self):
        """Verifica que mensaje vacío devuelve español."""
        mensaje = MensajeCreyente("")
        assert mensaje.idioma == "es"

    def test_deteccion_idioma_ingles_gana_a_espanol(self):
        """Verifica que si hay más palabras en inglés que español se detecta inglés."""
        mensaje = MensajeCreyente("Hello please help me queen of heaven")
        assert mensaje.idioma == "en"
