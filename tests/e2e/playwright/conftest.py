"""
Configuración de Playwright para pruebas E2E de UI.
"""
import asyncio
import threading
import time
from contextlib import asynccontextmanager

import pytest
import uvicorn
from la_santisima_conversacional.presentation import http_api


def _find_free_port():
    """Encuentra un puerto libre en localhost."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


class UvicornServer:
    """Servidor Uvicorn en un hilo."""
    def __init__(self, app, port):
        self.app = app
        self.port = port
        self.thread = None
        self.server = None
    
    def start(self):
        config = uvicorn.Config(self.app, host="127.0.0.1", port=self.port, log_level="warning")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run)
        self.thread.daemon = True
        self.thread.start()
        # Esperar a que el servidor esté listo
        for _ in range(30):
            try:
                import socket
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(1)
                    s.connect(("127.0.0.1", self.port))
                break
            except ConnectionRefusedError:
                time.sleep(0.1)
        else:
            raise RuntimeError("Server did not start within 3 seconds")
    
    def stop(self):
        if self.server:
            self.server.should_exit = True
        if self.thread:
            self.thread.join(timeout=5)


@pytest.fixture(scope="session")
def server_port():
    """Puerto libre para el servidor de prueba."""
    return _find_free_port()


@pytest.fixture(scope="session")
def server_url(server_port):
    """URL base del servidor de prueba."""
    return f"http://127.0.0.1:{server_port}"


@pytest.fixture(scope="session")
def live_server(server_port):
    """Arranca un servidor Uvicorn real en un hilo."""
    # Usamos la aplicación FastAPI del módulo http_api
    app = http_api.app
    server = UvicornServer(app, server_port)
    server.start()
    yield
    server.stop()


@pytest.fixture(scope="session")
def playwright_context_args(playwright_context_args, server_url):
    """Inyecta la URL base del servidor en los contextos de Playwright."""
    return {
        **playwright_context_args,
        "base_url": server_url,
    }