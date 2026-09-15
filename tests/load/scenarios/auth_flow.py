"""Escenario de carga: solo el camino de identidad (auth/sesión).

Aísla registro de dispositivo -> consentimiento -> creación de sesión del
resto del tráfico de mensajería, para validar ese camino bajo concurrencia
sin que el volumen de /api/v1/mensajes (mucho más pesado, golpea al LLM)
enmascare problemas específicos de auth (p. ej. contención en el registro
de dispositivos SQLite, o el rate limit de registro por IP).

Cada "usuario" de Locust aquí es un dispositivo que se registra una sola
vez y se detiene — no manda mensajes. Para generar volumen real, se
levanta con muchos usuarios y un ramp-up rápido (el registro es la tarea
única, no hay wait_time que la diluya).

Uso:
    locust -f tests/load/scenarios/auth_flow.py --host http://127.0.0.1:8000 \
        --headless -u 50 -r 50 -t 1m
"""

import logging

from locust import HttpUser, task

logger = logging.getLogger(__name__)


class UsuarioSoloAuth(HttpUser):
    """Registra un dispositivo, acepta el consentimiento vigente y crea una
    sesión — luego se detiene. No envía mensajes.
    """

    def on_start(self) -> None:
        self.registrar_y_autenticar()
        self.stop()

    def _headers(self, device_token: str) -> dict:
        return {"Authorization": f"Bearer {device_token}"}

    @task
    def registrar_y_autenticar(self) -> None:
        device_token = self._registrar_dispositivo()
        if device_token is None:
            return
        version = self._version_aviso_vigente()
        self._aceptar_consentimiento(device_token, version)
        self._crear_sesion(device_token)

    def _registrar_dispositivo(self) -> str | None:
        with self.client.post("/api/v1/dispositivos", json={}, catch_response=True) as resp:
            if resp.status_code == 429:
                logger.warning("Registro de dispositivo limitado por tasa (429).")
                resp.success()
                return None
            if resp.status_code != 200:
                resp.failure(f"Registro de dispositivo falló: {resp.status_code} {resp.text}")
                return None
            resp.success()
            return resp.json()["device_token"]

    def _version_aviso_vigente(self) -> str:
        with self.client.get("/privacidad", catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"GET /privacidad falló: {resp.status_code}")
                return "v1"
            resp.success()
            return resp.json()["version"]

    def _aceptar_consentimiento(self, device_token: str, version: str) -> None:
        with self.client.post(
            "/api/v1/dispositivos/consentimiento",
            json={"version": version},
            headers=self._headers(device_token),
            catch_response=True,
            name="/api/v1/dispositivos/consentimiento",
        ) as resp:
            if resp.status_code != 204:
                resp.failure(f"Consentimiento falló: {resp.status_code} {resp.text}")
            else:
                resp.success()

    def _crear_sesion(self, device_token: str) -> None:
        with self.client.post(
            "/api/v1/sesiones", headers=self._headers(device_token), catch_response=True
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"Creación de sesión falló: {resp.status_code} {resp.text}")
            else:
                resp.success()
