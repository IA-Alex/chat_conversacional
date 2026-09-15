"""Locust file principal — flujo completo de un cliente real contra la API.

Simula lo que hace la app real: se registra una vez (``on_start``), acepta
el aviso de privacidad vigente, abre una sesión, y luego pasa la mayor
parte del tiempo enviando mensajes (``/api/v1/mensajes``), con reinicios de
sesión y creación de sesiones nuevas ocasionales — igual que un creyente
que reinicia la conversación de vez en cuando pero mayormente sigue
hablando en la misma sesión.

Uso:
    locust -f tests/load/locustfile.py --host http://127.0.0.1:8000

Ver tests/load/README.md para escenarios específicos (auth puro, mensajería
sostenida, ráfaga de rate limit, degradación) — cada uno vive en
tests/load/scenarios/ como su propio locustfile independiente.
"""

import logging
import random

from locust import HttpUser, between, task

logger = logging.getLogger(__name__)

# Mensajes de ejemplo variados: evita que el LLM (o un caché delante de él)
# vea siempre el mismo prompt, que sería una carga poco representativa.
MENSAJES_EJEMPLO = [
    "Santísima Muerte, gracias por acompañarme hoy.",
    "Necesito fuerza para superar esta semana difícil.",
    "¿Qué oración me recomiendas para la protección?",
    "Siento miedo por mi salud, ¿me puedes ayudar?",
    "Quiero agradecer por lo que ya he recibido.",
    "Estoy triste, no sé qué hacer con mi vida.",
    "Dame esperanza para seguir adelante.",
    "¿Cómo puedo pedir por mi familia?",
]


class UsuarioConversacional(HttpUser):
    """Un dispositivo/usuario final completo: registro -> consentimiento ->
    sesión -> mensajería sostenida, con reinicios/nuevas sesiones ocasionales.
    """

    # Espera entre tareas: aproxima el ritmo de alguien escribiendo y
    # leyendo una respuesta, no un bucle cerrado golpeando el endpoint.
    wait_time = between(2, 6)

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
            if resp.status_code == 429:
                logger.warning("Registro de dispositivo limitado por tasa (429).")
                resp.success()  # Esperado bajo carga alta: no es un fallo del sistema.
                return
            if resp.status_code != 200:
                resp.failure(f"Registro de dispositivo falló: {resp.status_code} {resp.text}")
                return
            data = resp.json()
            self.device_id = data["device_id"]
            self.device_token = data["device_token"]
            resp.success()

    def _version_aviso_vigente(self) -> str:
        with self.client.get("/privacidad", catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"GET /privacidad falló: {resp.status_code}")
                return "v1"
            resp.success()
            return resp.json()["version"]

    def _aceptar_consentimiento(self) -> None:
        version = self._version_aviso_vigente()
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

    @task(20)
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
                # El objetivo de este escenario incluye deliberadamente
                # disparar el rate limit en algún momento bajo carga alta —
                # no es un fallo del sistema, es el comportamiento esperado.
                logger.info("Mensaje limitado por tasa (429) para %s", self.session_id)
                resp.success()
            elif resp.status_code != 200:
                resp.failure(f"Mensaje falló: {resp.status_code} {resp.text}")
            else:
                resp.success()

    @task(2)
    def reiniciar_sesion(self) -> None:
        if self.device_token is None or self.session_id is None:
            return
        with self.client.post(
            f"/api/v1/sesiones/{self.session_id}/reiniciar",
            headers=self._headers(),
            catch_response=True,
            name="/api/v1/sesiones/{session_id}/reiniciar",
        ) as resp:
            if resp.status_code != 204:
                resp.failure(f"Reinicio de sesión falló: {resp.status_code} {resp.text}")
            else:
                resp.success()

    @task(1)
    def nueva_sesion(self) -> None:
        if self.device_token is None:
            return
        self._crear_sesion()
