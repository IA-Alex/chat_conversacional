"""Escenario de carga: saturación de conexiones contra Postgres.

Existe por una razón concreta y distinta a los otros escenarios:
``PostgresConversationRepository`` abre **una conexión nueva por operación**
(no usa pool — ver el docstring de la clase). Bajo muchos usuarios
concurrentes, lo primero que se agota no es la CPU ni el LLM, sino
``max_connections`` del servidor Postgres. El síntoma de eso NO es un 500
con un mensaje claro: es un ``FATAL: sorry, too many clients already``
dentro de la capa de persistencia, que el cliente ve como un timeout o un
504 del proxy — indistinguible de "el LLM va lento".

Este escenario hace visible ese límite: 100 usuarios concurrentes
mandando mensajes sin pausa (lo que mantiene muchas conexiones abiertas a
la vez) mientras se lee ``GET /metrics/health`` para observar
``db_connection_pool_active_connections`` en vivo.

**Requiere el backend con Postgres**, no SQLite:

.. code-block:: bash

    SANTISIMA_USAR_POSTGRES=true \\
    SANTISIMA_POSTGRES_DSN=postgresql://postgres:postgres@127.0.0.1:5432/la_santisima \\
        uvicorn la_santisima_conversacional.presentation.http_api:app

Si ``db_backend`` reporta ``"sqlite"``, este escenario no está probando lo
que dice probar (SQLite es un archivo con lock, no un servidor con
``max_connections``). El listener de ``test_stop`` lo verifica y falla la
corrida con exit code != 0, para que un escenario que no midió nada no
pase como verde.

Uso:

.. code-block:: bash

    locust -f tests/load/scenarios/db_pool_test.py --headless \\
        -u 100 -r 20 -t 5m --host http://127.0.0.1:8000 \\
        --csv tests/load/resultados/db_pool

Ver tests/load/README.md para el resto de escenarios.
"""

import logging

from locust import HttpUser, constant, events, task

logger = logging.getLogger(__name__)

# Máximo de conexiones activas visto durante la corrida. Locust no tiene un
# mecanismo para agregar métricas arbitrarias por usuario, así que el
# sondeo de salud escribe aquí y el listener de test_stop lo reporta.
_max_conexiones_observadas = {"valor": 0}
_backends_vistos: set = set()


class UsuarioMensajeriaIntensiva(HttpUser):
    """Mensajería sin pausa: a diferencia de messaging_flow.py, aquí SÍ se
    quiere mantener muchas conexiones a la BD abiertas simultáneamente —
    es el punto del escenario. El 429 por rate limit se cuenta como
    esperado (no es lo que se está midiendo)."""

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
            if resp.status_code == 429:
                resp.success()  # Rate limit de registro por IP: esperado aquí.
                return
            if resp.status_code != 200:
                resp.failure(f"Registro de dispositivo falló: {resp.status_code} {resp.text}")
                return
            self.device_token = resp.json()["device_token"]
            resp.success()

    def _aceptar_consentimiento(self) -> None:
        with self.client.get("/privacidad", catch_response=True) as resp:
            version = resp.json().get("version", "v1") if resp.status_code == 200 else "v1"
            (
                resp.success()
                if resp.status_code == 200
                else resp.failure(f"GET /privacidad falló: {resp.status_code}")
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
        with self.client.post(
            "/api/v1/mensajes",
            json={"mensaje": "Santísima, acompáñame.", "session_id": self.session_id},
            headers=self._headers(),
            catch_response=True,
            name="/api/v1/mensajes",
        ) as resp:
            if resp.status_code in (200, 429):
                resp.success()
            else:
                resp.failure(f"Mensaje falló con {resp.status_code}: {resp.text}")


class UsuarioSondeoPool(HttpUser):
    """Lee ``/metrics/health`` para observar el conteo de conexiones activas.

    Es un usuario aparte (no una tarea dentro del anterior) para que sondee
    a ritmo constante aunque la carga de mensajería se sature y bloquee a
    esos usuarios: si el sondeo estuviera dentro del usuario de mensajería,
    justo cuando hay saturación (el momento que interesa medir) dejaría de
    reportar.
    """

    wait_time = constant(2)

    @task
    def sondear_pool(self) -> None:
        with self.client.get(
            "/metrics/health", catch_response=True, name="/metrics/health"
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"/metrics/health devolvió {resp.status_code}")
                return
            cuerpo = resp.json()
            _backends_vistos.add(cuerpo.get("db_backend"))
            activas = cuerpo.get("db_connection_pool_active_connections") or 0
            if activas > _max_conexiones_observadas["valor"]:
                _max_conexiones_observadas["valor"] = activas
                logger.info("Conexiones activas a la BD: %d", activas)
            resp.success()


@events.test_stop.add_listener
def _reportar_pool(environment, **kwargs) -> None:  # type: ignore[no-untyped-def]
    maximo = _max_conexiones_observadas["valor"]
    print(f"\n[db_pool_test] Máximo de conexiones activas observadas: {maximo}\n")

    if "sqlite" in _backends_vistos:
        # No es un fallo de la app: es un escenario mal configurado. Se
        # falla explícitamente para que nadie lea un "% de error bajo" como
        # validación de un pool que nunca se ejercitó.
        logger.error(
            "db_pool_test corrió contra SQLite (db_backend=sqlite): este escenario "
            "solo mide algo con SANTISIMA_USAR_POSTGRES=true."
        )
        print(
            "[db_pool_test] ERROR: el backend reporta db_backend=sqlite. "
            "Arranca el servidor con SANTISIMA_USAR_POSTGRES=true y "
            "SANTISIMA_POSTGRES_DSN apuntando a un Postgres real.\n"
        )
        environment.process_exit_code = 1
    elif maximo == 0:
        logger.warning(
            "db_pool_test no observó ninguna conexión activa: ¿el sondeo de "
            "/metrics/health corrió durante la carga?"
        )
