"""
conftest para pruebas E2E. Proporciona fixtures compartidos con el resto del suite.
"""
import importlib
import sys

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient


ADMIN_API_KEY = "test-admin-key"


@pytest.fixture()
def cliente(monkeypatch):
    """Fixture de cliente HTTP con mocks mejorados para pruebas BDD."""
    monkeypatch.setenv("DEEPINFRA_API_KEY", "sk-test")
    monkeypatch.setenv("SANTISIMA_API_KEYS", ADMIN_API_KEY)
    monkeypatch.setenv("SANTISIMA_SESSION_SECRET", "secreto-de-test")
    monkeypatch.setenv("SANTISIMA_USE_LANGCHAIN", "true")  # evita depender de crewai real
    monkeypatch.setenv("SANTISIMA_USAR_SQLITE", "false")  # repositorio en memoria
    monkeypatch.setenv("SANTISIMA_RATE_LIMIT_POR_MINUTO", "2")
    monkeypatch.setenv("SANTISIMA_DEBUG", "false")
    monkeypatch.setenv("SANTISIMA_CLAVE_CIFRADO", Fernet.generate_key().decode())

    from la_santisima_conversacional import config as config_module

    config_module.get_settings.cache_clear()

    for nombre in ("la_santisima_conversacional.presentation.http_api",):
        sys.modules.pop(nombre, None)
    http_api = importlib.import_module("la_santisima_conversacional.presentation.http_api")

    with TestClient(http_api.app) as client:
        # Reemplaza el motor real (LangChainAdapter con stubs de conftest)
        # por un doble de prueba: los tests de esta capa validan HTTP
        # (auth, rate limit, propiedad de sesión), no el motor de IA —
        # eso ya está cubierto por test_langchain_adapter.py.
        servicio = client.app.state.api.caso_de_uso.servicio_respuestas
        servicio.esta_degradado = False

        def _generar_respuesta(mensaje):
            if hasattr(mensaje, 'contenido'):
                texto = mensaje.contenido
            else:
                texto = str(mensaje)
            mensaje_lower = texto.lower()
            if "hola" in mensaje_lower:
                contenido = "Bienvenida, creyente. Te ofrezco consuelo y apoyo."
                emocion = "devocion"
            elif "miedo" in mensaje_lower:
                contenido = "La Santísima Muerte te acompaña en tu miedo. Eleva una oración."
                emocion = "consuelo"
            else:
                contenido = "Bienvenida, creyente. Te ofrezco consuelo y apoyo."
                emocion = "devocion"
            class _RespuestaFalsa:
                def __init__(self, contenido, modelo, emocion):
                    self.contenido = contenido
                    self.modelo = modelo
                    self.emocion = emocion
            return _RespuestaFalsa(contenido, "modelo-de-prueba", emocion)

        def _responder_mensaje(mensaje, historial=None, on_resumen_actualizado=None):
            return _generar_respuesta(mensaje)

        def _responder_mensaje_stream(mensaje, historial=None, on_resumen_actualizado=None):
            respuesta = _generar_respuesta(mensaje)
            # Dividir contenido en chunks para streaming
            contenido = respuesta.contenido
            if contenido.startswith("Bienvenida"):
                yield "Hola "
                yield "creyente."
            else:
                # Para otros mensajes, dividir en palabras
                palabras = contenido.split()
                for palabra in palabras:
                    yield palabra + " "
            return respuesta.emocion

        servicio.responder_mensaje = _responder_mensaje
        servicio.responder_mensaje_stream = _responder_mensaje_stream

        yield client

    config_module.get_settings.cache_clear()


# También podemos agregar fixtures específicos para E2E
@pytest.fixture(scope="session")
def playwright_context_args(playwright_context_args):
    """Personalizar argumentos del contexto de Playwright para tests E2E."""
    return {
        **playwright_context_args,
        "viewport": {"width": 1280, "height": 720},
        "ignore_https_errors": True,
    }