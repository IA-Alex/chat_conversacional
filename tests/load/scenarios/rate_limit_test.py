"""Escenario de carga: ráfaga deliberada para confirmar que el rate limit
por dispositivo (``settings.rate_limit_por_minuto``, 20/min por defecto)
efectivamente devuelve 429 al excederse.

A diferencia de messaging_flow.py (que evita a propósito tocar el límite),
este escenario existe para dispararlo: un solo dispositivo registrado una
vez, mandando mensajes con una espera mínima. Con 25 usuarios concurrentes
todos autenticados como SU PROPIO dispositivo (el límite es por
device_id, no global), lo relevante no es que cada usuario individual
supere 20/min, sino confirmar que el propio mecanismo responde 429 cuando
UN dispositivo sí lo hace — por eso ``UsuarioRafagaUnDispositivo`` reduce
su ``wait_time`` a casi cero: cada usuario simulado, por sí solo, manda muy
por encima de 20 mensajes/min y debe ver 429 antes del minuto.

Al final de la corrida, un listener de ``test_stop`` imprime cuántos 429
se observaron y falla la corrida (exit code != 0) si no se observó
ninguno — sin eso, un límite roto (p. ej. desactivado por error) pasaría
inadvertido en un resumen que solo mira % de error total.

Uso:
    locust -f tests/load/scenarios/rate_limit_test.py --headless \
        -u 25 -r 25 -t 30s --host http://127.0.0.1:8000
"""

import logging

from locust import HttpUser, constant, events, task

logger = logging.getLogger(__name__)

_contador_429 = {"total": 0}


class UsuarioRafagaUnDispositivo(HttpUser):
    """Un dispositivo propio por usuario simulado, mandando mensajes sin
    apenas pausa — deliberadamente por encima del límite por minuto.
    """

    wait_time = constant(0.2)

    def on_start(self) -> None:
        self.device_token = None
        self.session_id = None
        self._registrar_dispositivo()
        if self.device_token is None:
            return
        self._aceptar_consentimiento()
        self._crear_sesion()

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.device_token}"}

    def _registrar_dispositivo(self) -> None:
        with self.client.post("/api/v1/dispositivos", json={}, catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"Registro de dispositivo falló: {resp.status_code} {resp.text}")
                return
            self.device_token = resp.json()["device_token"]
            resp.success()

    def _aceptar_consentimiento(self) -> None:
        with self.client.get("/privacidad", catch_response=True) as resp:
            version = resp.json().get("version", "v1") if resp.status_code == 200 else "v1"
            resp.success() if resp.status_code == 200 else resp.failure(
                f"GET /privacidad falló: {resp.status_code}"
            )
        with self.client.post(
            "/api/v1/dispositivos/consentimiento",
            json={"version": version},
            headers=self._headers(),
            catch_response=True,
            name="/api/v1/dispositivos/consentimiento",
        ) as resp:
            if resp.status_code != 204:
                resp.failure(f"Consentimiento falló: {resp.status_code} {resp.text}")
            else:
                resp.success()

    def _crear_sesion(self) -> None:
        with self.client.post(
            "/api/v1/sesiones", headers=self._headers(), catch_response=True
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"Creación de sesión falló: {resp.status_code} {resp.text}")
                return
            self.session_id = resp.json()["session_id"]
            resp.success()

    @task
    def enviar_mensaje_rafaga(self) -> None:
        if self.device_token is None or self.session_id is None:
            return
        with self.client.post(
            "/api/v1/mensajes",
            json={"mensaje": "Hola, Santísima.", "session_id": self.session_id},
            headers=self._headers(),
            catch_response=True,
            name="/api/v1/mensajes",
        ) as resp:
            if resp.status_code == 429:
                _contador_429["total"] += 1
                resp.success()  # Es exactamente lo que este escenario busca provocar.
            elif resp.status_code != 200:
                resp.failure(f"Mensaje falló: {resp.status_code} {resp.text}")
            else:
                resp.success()


@events.test_stop.add_listener
def _reportar_429(environment, **kwargs) -> None:  # type: ignore[no-untyped-def]
    total = _contador_429["total"]
    if total > 0:
        logger.info("rate_limit_test: %d respuestas 429 observadas (esperado).", total)
        print(f"\n[rate_limit_test] 429 observados: {total} -- limite funcionando correctamente.\n")
    else:
        logger.error(
            "rate_limit_test: NINGUNA respuesta 429 observada -- el rate limit por "
            "dispositivo podria estar roto o deshabilitado."
        )
        print(
            "\n[rate_limit_test] ADVERTENCIA: 0 respuestas 429 observadas. "
            "Se esperaba al menos una bajo esta rafaga -- revisar "
            "settings.rate_limit_por_minuto y el limitador configurado.\n"
        )
        environment.process_exit_code = 1
