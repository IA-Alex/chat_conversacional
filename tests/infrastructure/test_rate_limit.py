"""Tests para el limitador de tasa en memoria."""

from la_santisima_conversacional.infrastructure.rate_limit import LimitadorTasa


class TestLimitadorTasa:
    def test_permite_hasta_el_limite(self):
        limitador = LimitadorTasa(limite=3, ventana_segundos=60)
        assert limitador.permitir("clave") is True
        assert limitador.permitir("clave") is True
        assert limitador.permitir("clave") is True

    def test_rechaza_al_exceder_el_limite(self):
        limitador = LimitadorTasa(limite=2, ventana_segundos=60)
        limitador.permitir("clave")
        limitador.permitir("clave")
        assert limitador.permitir("clave") is False

    def test_claves_distintas_no_comparten_cupo(self):
        limitador = LimitadorTasa(limite=1, ventana_segundos=60)
        assert limitador.permitir("a") is True
        assert limitador.permitir("b") is True
        assert limitador.permitir("a") is False

    def test_expira_eventos_fuera_de_la_ventana(self):
        limitador = LimitadorTasa(limite=1, ventana_segundos=0.05)
        assert limitador.permitir("clave") is True
        assert limitador.permitir("clave") is False
        import time

        time.sleep(0.06)
        assert limitador.permitir("clave") is True
