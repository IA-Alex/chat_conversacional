"""Escenario de carga: mensajería sostenida dentro del límite por dispositivo.

Este es el escenario para el objetivo principal de carga sostenida (ver
tests/load/README.md): 100 usuarios concurrentes, ramp-up de 5 minutos,
30 minutos sostenidos, p95 < 3s, tasa de error < 1%.

Cada usuario simulado representa UN dispositivo, y ``wait_time`` se elige
para que ese dispositivo se quede cómodamente por debajo de
``settings.rate_limit_por_minuto`` (20/min por defecto): con una espera
mínima de 5s entre mensajes, un usuario manda como mucho 12/min — nunca
dispara 429 por sí solo. El objetivo de este escenario es medir latencia y
tasa de error bajo carga realista, no el rate limit (para eso está
rate_limit_test.py).
"""

import logging
import random

from locust import HttpUser, between, task

logger = logging.getLogger(__name__)

MENSAJES_EJEMPLO = [
    "Santísima Muerte, gracias por acompañarme hoy.",
    "Necesito fuerza para superar esta semana difícil.",
    "¿Qué oración me recomiendas para la protección?",
    "Siento miedo por mi salud, ¿me puedes ayudar?",
    "Quiero agradecer por lo que ya he recibido.",
    "Estoy triste, no sé qué hacer con mi vida.",
]


class UsuarioMensajeriaSostenida(HttpUser):
    """Registro + consentimiento + sesión una vez, luego mensajes espaciados
    para quedarse muy por debajo del límite por minuto.
    """

    # 5-8s entre mensajes: ~7.5-12 mensajes/min por usuario, bien debajo del
    # límite (20/min) incluso con jitter. Deliberadamente NO usa
    # ``constant`` para no generar un patrón perfectamente sincronizado
    # entre todos los usuarios simulados.
    wait_time = between(5, 8)

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
            data = resp.json()
            self.device_token = data["device_token"]
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
            if resp.status_code == 429:
                # Bajo ritmo controlado esto NO debería pasar; si aparece,
                # cuenta como fallo aquí (a diferencia de locustfile.py /
                # rate_limit_test.py) porque indica que el ritmo elegido ya
                # no está realmente debajo del límite configurado.
                resp.failure("429 inesperado bajo ritmo controlado (revisar rate_limit_por_minuto)")
            elif resp.status_code != 200:
                resp.failure(f"Mensaje falló: {resp.status_code} {resp.text}")
            else:
                resp.success()
