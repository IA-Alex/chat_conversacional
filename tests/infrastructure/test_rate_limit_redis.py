"""Tests de integración para LimitadorTasaRedis.

Levanta un ``redis-server`` efímero para el módulo de tests (no se mockea
el cliente Redis: el valor de esta clase está en la atomicidad real del
script Lua bajo concurrencia, que un mock no puede validar). Se salta
automáticamente si no hay binario ``redis-server`` disponible o el import
de ``redis`` falla — no rompe CI en entornos sin Redis, consistente con
que esta funcionalidad está apagada por defecto
(``Settings.usar_redis_rate_limit``).
"""

import shutil
import socket
import subprocess
import time

import pytest

redis = pytest.importorskip("redis", reason="requiere el extra 'redis'")

from la_santisima_conversacional.infrastructure.rate_limit import (  # noqa: E402
    LimitadorTasaRedis,
)

pytestmark = pytest.mark.skipif(
    shutil.which("redis-server") is None, reason="binario redis-server no disponible"
)


def _puerto_libre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def redis_url():
    puerto = _puerto_libre()
    proceso = subprocess.Popen(
        ["redis-server", "--port", str(puerto), "--daemonize", "no", "--save", ""],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"redis://127.0.0.1:{puerto}/0"
    try:
        cliente = redis.Redis.from_url(url)
        for _ in range(50):
            try:
                if cliente.ping():
                    break
            except redis.ConnectionError:
                time.sleep(0.1)
        else:
            pytest.fail("redis-server efímero no respondió a tiempo")
        yield url
    finally:
        proceso.terminate()
        proceso.wait(timeout=5)


@pytest.fixture
def limitador(redis_url):
    lim = LimitadorTasaRedis(limite=3, ventana_segundos=60, redis_url=redis_url)
    lim._cliente.flushdb()
    return lim


class TestLimitadorTasaRedis:
    def test_permite_hasta_el_limite(self, limitador):
        assert limitador.permitir("clave") is True
        assert limitador.permitir("clave") is True
        assert limitador.permitir("clave") is True

    def test_rechaza_al_exceder_el_limite(self, limitador):
        for _ in range(3):
            limitador.permitir("clave")
        assert limitador.permitir("clave") is False

    def test_claves_distintas_no_comparten_cupo(self, limitador):
        for _ in range(3):
            limitador.permitir("a")
        assert limitador.permitir("a") is False
        assert limitador.permitir("b") is True

    def test_expira_eventos_fuera_de_la_ventana(self, redis_url):
        lim = LimitadorTasaRedis(limite=1, ventana_segundos=0.2, redis_url=redis_url)
        lim._cliente.flushdb()
        assert lim.permitir("clave") is True
        assert lim.permitir("clave") is False
        time.sleep(0.3)
        assert lim.permitir("clave") is True

    def test_es_correcto_bajo_llamadas_concurrentes(self, redis_url):
        """El escenario que justifica esta clase sobre LimitadorTasa: con
        varias 'instancias' (aquí, threads golpeando el mismo Redis a la
        vez) el límite debe respetarse exactamente, sin la carrera
        check-then-act que rompería un conteo no atómico."""
        import threading

        lim = LimitadorTasaRedis(limite=10, ventana_segundos=60, redis_url=redis_url)
        lim._cliente.flushdb()

        permitidos = []
        lock = threading.Lock()

        def intentar():
            resultado = lim.permitir("clave-compartida")
            with lock:
                permitidos.append(resultado)

        hilos = [threading.Thread(target=intentar) for _ in range(30)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()

        assert sum(permitidos) == 10
