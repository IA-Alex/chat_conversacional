"""Escenario de carga: valida que el servicio se mantenga respondiendo
(aunque sea degradado) bajo carga, en vez de caerse.

Combina dos tipos de usuario en la misma corrida:

- ``UsuarioSondeoSalud``: solo repite GET /health/ready y GET /metrics/health
  sin autenticarse (ambos son públicos) — sirve para observar en vivo si el
  motor de IA entra en modo degradado (``llm_adapter_status``: "degraded",
  o 503 de /health/ready) durante la corrida, y que esos endpoints en sí
  mismos sigan respondiendo bajo la misma carga que estresa /api/v1/mensajes.
- ``UsuarioMensajeriaConcurrente``: dispositivo real mandando mensajes en
  paralelo al sondeo de salud, para generar la carga que podría llevar al
  motor de IA a degradarse (p. ej. el proveedor LLM fallando o con
  latencia alta).

A diferencia de rate_limit_test.py, aquí un 429 en /api/v1/mensajes SÍ se
cuenta como estado esperado (no es el foco), pero un 5xx en /health o
/health/ready sí se marca como fallo: ese es justamente el síntoma que
este escenario existe para detectar (el proceso cayéndose, no solo
degradándose).

Uso:
    locust -f tests/load/scenarios/degradation_flow.py --headless \
        -u 20 -r 10 -t 5m --host http://127.0.0.1:8000
"""

import logging
import random

from locust import HttpUser, between, task

logger = logging.getLogger(__name__)

MENSAJES_EJEMPLO = [
    "Santísima Muerte, acompáñame en este momento.",
    "Pido protección para mi familia.",
    "Gracias por escucharme.",
]


class UsuarioSondeoSalud(HttpUser):
    """Solo polling de salud, sin autenticación — igual que lo haría un
    orquestador (Kubernetes, un load balancer) vigilando la instancia.
    """

    wait_time = between(1, 3)

    @task(2)
    def health_ready(self) -> None:
        with self.client.get(
            "/health/ready", catch_response=True, name="/health/ready"
        ) as resp:
            if resp.status_code in (200, 503):
                # 503 es "degradado pero respondiendo" -- comportamiento
                # correcto bajo este escenario, no un fallo.
                resp.success()
            else:
                resp.failure(f"/health/ready devolvió {resp.status_code} (inesperado)")

    @task(2)
    def metrics_health(self) -> None:
        with self.client.get(
            "/metrics/health", catch_response=True, name="/metrics/health"
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"/metrics/health devolvió {resp.status_code}")
                return
            estado = resp.json().get("llm_adapter_status")
            if estado == "degraded":
                logger.warning("Motor de IA reportado como degradado durante la corrida.")
            resp.success()

    @task(1)
    def health_liveness(self) -> None:
        with self.client.get("/health", catch_response=True, name="/health") as resp:
            if resp.status_code != 200:
                resp.failure(f"/health devolvió {resp.status_code} (el proceso no responde bien)")
            else:
                resp.success()


class UsuarioMensajeriaConcurrente(HttpUser):
    """Genera carga real de mensajería en paralelo al sondeo de salud."""

    wait_time = between(3, 6)

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
    def enviar_mensaje(self) -> None:
        if self.device_token is None or self.session_id is None:
            return
        mensaje = random.choice(MENSAJES_EJEMPLO)
        with self.client.post(
            "/api/v1/mensajes",
            json={"mensaje": mensaje, "session_id": self.session_id},
            headers=self._headers(),
            catch_response=True,
            name="/api/v1/mensajes",
        ) as resp:
            if resp.status_code in (200, 429):
                # 429 no es el foco de este escenario (ver rate_limit_test.py);
                # lo relevante aquí es que el servicio siga en pie.
                resp.success()
            else:
                resp.failure(f"Mensaje falló: {resp.status_code} {resp.text}")
