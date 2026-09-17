"""Tests de humo para la capa HTTP: identidad por dispositivo, admin,
rate limit, propiedad de sesión, salud.

``http_api.app`` se construye al importar el módulo (para que uvicorn lo
encuentre como ``module:app``), así que este archivo fija las variables de
entorno requeridas *antes* de importar — igual que tendría que hacerlo un
proceso real al arrancar.
"""

import importlib
import sys

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

ADMIN_API_KEY = "test-admin-key"


@pytest.fixture()
def cliente(monkeypatch):
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

        class _RespuestaFalsa:
            contenido = "Respuesta de prueba."
            modelo = "modelo-de-prueba"
            emocion = "devocion"

        def _responder_mensaje(mensaje, historial=None, on_resumen_actualizado=None):
            return _RespuestaFalsa()

        def _responder_mensaje_stream(mensaje, historial=None, on_resumen_actualizado=None):
            yield "Hola "
            yield "creyente."
            return "devocion"

        servicio.responder_mensaje = _responder_mensaje
        servicio.responder_mensaje_stream = _responder_mensaje_stream

        yield client

    config_module.get_settings.cache_clear()


def _admin_headers() -> dict:
    return {"Authorization": f"Bearer {ADMIN_API_KEY}"}


def _registrar_dispositivo(cliente) -> dict:
    """Helper: registra un dispositivo nuevo, devuelve {device_id, device_token}."""
    resp = cliente.post("/api/v1/dispositivos")
    assert resp.status_code == 200
    return resp.json()


def _aceptar_consentimiento(cliente, headers: dict) -> None:
    """Helper: acepta el aviso de privacidad vigente para un dispositivo ya
    registrado. La versión se lee de GET /privacidad (no se hardcodea) para
    que el test siga funcionando si SANTISIMA_AVISO_PRIVACIDAD_VERSION cambia.
    """
    version = cliente.get("/privacidad").json()["version"]
    resp = cliente.post(
        "/api/v1/dispositivos/consentimiento", json={"version": version}, headers=headers
    )
    assert resp.status_code == 204


def _device_headers(cliente) -> dict:
    """Dispositivo registrado y CON consentimiento ya aceptado: la mayoría
    de los tests de esta capa no están probando el gate de consentimiento
    en sí (eso vive en TestConsentimiento) — necesitan pasar de largo ese
    paso para probar lo que realmente les interesa (propiedad de sesión,
    rate limit, etc.)."""
    dispositivo = _registrar_dispositivo(cliente)
    headers = {"Authorization": f"Bearer {dispositivo['device_token']}"}
    _aceptar_consentimiento(cliente, headers)
    return headers, dispositivo


class TestSalud:
    def test_health_no_requiere_auth(self, cliente):
        resp = cliente.get("/health")
        assert resp.status_code == 200

    def test_readiness_ok_cuando_no_degradado(self, cliente):
        resp = cliente.get("/health/ready")
        assert resp.status_code == 200

    def test_readiness_503_cuando_motor_degradado(self, cliente):
        cliente.app.state.api.caso_de_uso.servicio_respuestas.esta_degradado = True
        resp = cliente.get("/health/ready")
        assert resp.status_code == 503

    def test_metrics_expone_formato_prometheus(self, cliente):
        resp = cliente.get("/metrics")
        assert resp.status_code == 200
        assert "santisima_http_requests_total" in resp.text

    def test_metrics_health_no_requiere_auth(self, cliente):
        resp = cliente.get("/metrics/health")
        assert resp.status_code == 200
        cuerpo = resp.json()
        assert cuerpo["llm_adapter_status"] == "ok"
        assert cuerpo["db_backend"] == "sqlite"
        assert cuerpo["ultima_purga"] is None

    def test_metrics_health_refleja_degradacion(self, cliente):
        cliente.app.state.api.caso_de_uso.servicio_respuestas.esta_degradado = True
        cliente.get("/health/ready")  # actualiza el gauge, igual que un scrape real
        resp = cliente.get("/metrics/health")
        assert resp.json()["llm_adapter_status"] == "degraded"


class TestMetricasDeOperacion:
    """Campos de observabilidad agregados en la auditoría post-deployment
    (ver monitoring/README.md y docs/runbooks/HEALTH_CHECKS.md): pool de
    conexiones BD, estado de Redis, tamaño del historial y duración/recuento
    de sesiones. Sin estos, "¿cuántas conversaciones hay abiertas?", "¿el
    historial crece sin control?" y "¿Redis está caído?" solo se respondían
    entrando al servidor a mano."""

    def test_metrics_health_incluye_campos_de_operacion(self, cliente):
        """Todos los campos que documenta HEALTH_CHECKS.md están presentes.

        Se afirman las claves (no solo el status 200) porque el modo de
        falla realista no es un 500, sino un campo que desaparece del JSON:
        un dashboard que lee `db_connection_pool_active_connections` se
        rompe en silencio si el endpoint deja de devolverlo.
        """
        resp = cliente.get("/metrics/health")
        assert resp.status_code == 200
        cuerpo = resp.json()
        for campo in (
            "llm_adapter_status",
            "db_backend",
            "db_connection_pool_active_connections",
            "db_historial_filas",
            "sesiones_activas",
            "redis_rate_limit_enabled",
            "redis_connection_status",
            "ultima_purga",
        ):
            assert campo in cuerpo, f"falta el campo '{campo}' en /metrics/health"

    def test_redis_disabled_cuando_no_esta_configurado(self, cliente):
        """Sin usar_redis_rate_limit, el estado es "disabled" (no un error):
        es la configuración correcta en single-instance (ver SCALING.md)."""
        cuerpo = cliente.get("/metrics/health").json()
        assert cuerpo["redis_rate_limit_enabled"] is False
        assert cuerpo["redis_connection_status"] == "disabled"

    def test_historial_filas_es_none_con_repositorio_en_memoria(self, cliente):
        """`None` ≠ 0: el repositorio en memoria no implementa `contar_filas`,
        así que el dato es "no medido" y no "historial vacío"."""
        assert cliente.get("/metrics/health").json()["db_historial_filas"] is None

    def test_sesiones_activas_empieza_en_cero(self, cliente):
        assert cliente.get("/metrics/health").json()["sesiones_activas"] == 0

    def test_crear_sesion_incrementa_sesiones_activas(self, cliente):
        headers, _ = _device_headers(cliente)
        resp = cliente.post("/api/v1/sesiones", headers=headers)
        assert resp.status_code == 200
        assert cliente.get("/metrics/health").json()["sesiones_activas"] == 1

    def test_pool_de_conexiones_es_cero_en_sqlite(self, cliente):
        """SQLite es un archivo, no un servidor: no hay conexiones
        concurrentes que medir (ver el comentario en http_api.py)."""
        cuerpo = cliente.get("/metrics/health").json()
        assert cuerpo["db_backend"] == "sqlite"
        assert cuerpo["db_connection_pool_active_connections"] == 0

    def test_reiniciar_sesion_cierra_y_observa_duracion(self, cliente):
        """Crear → reiniciar devuelve sesiones_activas a 0 y registra una
        observación en el histograma de duración. Antes no había ninguna
        métrica de duración de sesión (requisito explícito de la auditoría)."""
        headers, _ = _device_headers(cliente)
        session_id = cliente.post("/api/v1/sesiones", headers=headers).json()["session_id"]
        assert cliente.get("/metrics/health").json()["sesiones_activas"] == 1

        resp = cliente.post(f"/api/v1/sesiones/{session_id}/reiniciar", headers=headers)
        assert resp.status_code == 204
        assert cliente.get("/metrics/health").json()["sesiones_activas"] == 0

        # El histograma es global del proceso, así que se comprueba que la
        # serie existe (los tests de esta clase comparten el registro
        # Prometheus y el conteo exacto dependería del orden de ejecución).
        assert "santisima_session_duration_seconds_count" in cliente.get("/metrics").text

    def test_degradacion_incrementa_contador_de_eventos(self, cliente):
        """`santisima_llm_degradation_events_total` cuenta TRANSICIONES a
        degradado, no el estado (para eso está el gauge): así se distingue
        "degradado desde el arranque" de "se degradó y se recuperó 40 veces"."""
        servicio = cliente.app.state.api.caso_de_uso.servicio_respuestas
        antes = _valor_metrica(cliente.get("/metrics").text, "santisima_llm_degradation_events")

        servicio.esta_degradado = True
        cliente.get("/health/ready")
        cliente.get("/health/ready")  # segundo poll: NO debe contar como otra entrada

        despues = _valor_metrica(cliente.get("/metrics").text, "santisima_llm_degradation_events")
        assert despues == antes + 1, "una transición debe contar exactamente una vez"

    def test_recuperacion_de_degradacion_no_cuenta_evento(self, cliente):
        """Volver a 0 no incrementa el contador de entradas (es una salida)."""
        servicio = cliente.app.state.api.caso_de_uso.servicio_respuestas
        servicio.esta_degradado = True
        cliente.get("/health/ready")
        durante = _valor_metrica(cliente.get("/metrics").text, "santisima_llm_degradation_events")

        servicio.esta_degradado = False
        cliente.get("/health/ready")
        tras_recuperar = _valor_metrica(
            cliente.get("/metrics").text, "santisima_llm_degradation_events"
        )
        assert tras_recuperar == durante


def _valor_metrica(texto_prometheus: str, nombre: str) -> int:
    """Extrae el valor de un contador sin labels del texto de /metrics.

    Devuelve 0 si la serie todavía no existe (un contador sin incrementos
    no se expone), así el test compara "cambió en 1" sin depender de que la
    suite haya ejercitado antes ese camino.
    """
    for linea in texto_prometheus.splitlines():
        if linea.startswith(f"{nombre}_total ") or linea.startswith(f"{nombre} "):
            return int(float(linea.rsplit(" ", 1)[1]))
    return 0


class TestRegistroDeDispositivo:
    def test_registrar_dispositivo_no_requiere_auth(self, cliente):
        resp = cliente.post("/api/v1/dispositivos")
        assert resp.status_code == 200
        data = resp.json()
        assert "device_id" in data
        assert "device_token" in data

    def test_cada_registro_da_un_dispositivo_distinto(self, cliente):
        d1 = _registrar_dispositivo(cliente)
        d2 = _registrar_dispositivo(cliente)
        assert d1["device_id"] != d2["device_id"]
        assert d1["device_token"] != d2["device_token"]

    def test_registro_por_encima_del_limite_por_ip_devuelve_429(self, cliente, monkeypatch):
        """Protege el cupo del LLM: un bucle automatizado sin device_token
        no puede generar identidades sin límite desde la misma IP. El
        límite (ver SANTISIMA_RATE_LIMIT_REGISTRO_POR_MINUTO) es holgado a
        propósito, así que solo lo prueba con un tope bajo para no
        necesitar cientos de requests en el test."""
        monkeypatch.setenv("SANTISIMA_RATE_LIMIT_REGISTRO_POR_MINUTO", "2")

        from la_santisima_conversacional import config as config_module

        config_module.get_settings.cache_clear()
        import sys as _sys

        _sys.modules.pop("la_santisima_conversacional.presentation.http_api", None)
        http_api = importlib.import_module("la_santisima_conversacional.presentation.http_api")

        with TestClient(http_api.app) as cliente_limitado:
            assert cliente_limitado.post("/api/v1/dispositivos").status_code == 200
            assert cliente_limitado.post("/api/v1/dispositivos").status_code == 200
            resp = cliente_limitado.post("/api/v1/dispositivos")
            assert resp.status_code == 429

        config_module.get_settings.cache_clear()

    def test_endpoints_de_usuario_requieren_device_token(self, cliente):
        resp = cliente.post("/api/v1/sesiones")
        assert resp.status_code == 401

    def test_device_token_fabricado_es_rechazado(self, cliente):
        resp = cliente.post("/api/v1/sesiones", headers={"Authorization": "Bearer token-inventado"})
        assert resp.status_code == 401

    def test_device_token_de_otra_instalacion_del_servidor_es_rechazado(self, cliente, monkeypatch):
        """Un device_token firmado con OTRO session_secret (p. ej. de otro
        backend, o fabricado) nunca debe pasar la verificación de firma."""
        from la_santisima_conversacional.infrastructure.security import emitir_device_token
        from la_santisima_conversacional.config import Settings

        settings_ajenos = Settings(
            deepinfra_api_key="sk-test", session_secret="otro-secreto-totalmente-distinto"
        )
        token_ajeno = emitir_device_token("device-cualquiera", settings_ajenos)
        resp = cliente.post("/api/v1/sesiones", headers={"Authorization": f"Bearer {token_ajeno}"})
        assert resp.status_code == 401

    def test_device_token_huerfano_es_401_no_403(self, cliente):
        """Firma genuina (mismo session_secret que la app viva) pero un
        device_id que nunca pasó por `registrar()`: no es una revocación
        deliberada (nadie llamó al endpoint de admin), es un token
        huérfano — apuntando a un registro de dispositivos que nunca lo
        tuvo. Antes esto colapsaba en el mismo 403 que una revocación real
        (ver test_revocar_dispositivo_con_api_key_admin_lo_bloquea), lo que
        le impedía al cliente distinguir "puedo re-registrarme solo" de
        "esto está bloqueado a propósito, no debo bypasearlo"."""
        from la_santisima_conversacional.infrastructure.security import emitir_device_token

        settings_reales = cliente.app.state.settings
        token_huerfano = emitir_device_token("device-jamas-registrado", settings_reales)
        resp = cliente.post(
            "/api/v1/sesiones", headers={"Authorization": f"Bearer {token_huerfano}"}
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "device_token no reconocido."


class TestAdministracion:
    def test_revocar_dispositivo_sin_api_key_admin_devuelve_401(self, cliente):
        dispositivo = _registrar_dispositivo(cliente)
        resp = cliente.post(f"/admin/dispositivos/{dispositivo['device_id']}/revocar")
        assert resp.status_code == 401

    def test_revocar_dispositivo_con_api_key_admin_lo_bloquea(self, cliente):
        dispositivo = _registrar_dispositivo(cliente)
        headers = {"Authorization": f"Bearer {dispositivo['device_token']}"}

        # Antes de revocar, el dispositivo puede usar la API.
        assert cliente.post("/api/v1/sesiones", headers=headers).status_code == 200

        resp = cliente.post(
            f"/admin/dispositivos/{dispositivo['device_id']}/revocar", headers=_admin_headers()
        )
        assert resp.status_code == 204

        # Después de revocar, el mismo device_token deja de servir.
        resp = cliente.post("/api/v1/sesiones", headers=headers)
        assert resp.status_code == 403


class TestPropiedadDeSesion:
    def test_mensaje_con_session_id_ajeno_devuelve_404(self, cliente):
        """Un session_id inventado (o de otro dispositivo) no debe ser usable.

        Escenario central: antes cualquier string servía como session_id
        sin verificación de propiedad.
        """
        headers, _ = _device_headers(cliente)
        resp = cliente.post(
            "/api/v1/mensajes",
            json={"mensaje": "hola", "session_id": "session-inventada"},
            headers=headers,
        )
        assert resp.status_code == 404

    def test_mensaje_con_session_id_propio_funciona(self, cliente):
        headers, _ = _device_headers(cliente)
        session_id = cliente.post("/api/v1/sesiones", headers=headers).json()["session_id"]
        resp = cliente.post(
            "/api/v1/mensajes",
            json={"mensaje": "hola La Santísima", "session_id": session_id},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["respuesta"] == "Respuesta de prueba."
        assert resp.json()["emocion"] == "devocion"

    def test_session_id_de_un_dispositivo_no_sirve_para_otro(self, cliente):
        headers_a, _ = _device_headers(cliente)
        headers_b, _ = _device_headers(cliente)
        session_id_de_a = cliente.post("/api/v1/sesiones", headers=headers_a).json()["session_id"]

        resp = cliente.post(
            "/api/v1/mensajes",
            json={"mensaje": "hola", "session_id": session_id_de_a},
            headers=headers_b,
        )
        assert resp.status_code == 404

    def test_reiniciar_sesion_ajena_devuelve_404(self, cliente):
        headers, _ = _device_headers(cliente)
        resp = cliente.post("/api/v1/sesiones/session-inventada/reiniciar", headers=headers)
        assert resp.status_code == 404

    def test_reiniciar_sesion_propia_vacia_el_historial(self, cliente):
        """RF-017: a diferencia de test_reiniciar_sesion_ajena_devuelve_404
        (que solo prueba el rechazo), esto confirma que reiniciar una
        sesión propia sí borra el historial persistido."""
        headers, _ = _device_headers(cliente)
        session_id = cliente.post("/api/v1/sesiones", headers=headers).json()["session_id"]
        cliente.post(
            "/api/v1/mensajes",
            json={"mensaje": "hola La Santísima", "session_id": session_id},
            headers=headers,
        )
        repositorio = cliente.app.state.api.caso_de_uso.repositorio
        assert repositorio.get_history(session_id) != []

        resp = cliente.post(f"/api/v1/sesiones/{session_id}/reiniciar", headers=headers)
        assert resp.status_code == 204
        assert repositorio.get_history(session_id) == []


class TestRateLimit:
    def test_excede_limite_configurado(self, cliente):
        headers, _ = _device_headers(cliente)
        session_id = cliente.post("/api/v1/sesiones", headers=headers).json()["session_id"]
        payload = {"mensaje": "hola", "session_id": session_id}
        # SANTISIMA_RATE_LIMIT_POR_MINUTO=2 en el fixture.
        assert cliente.post("/api/v1/mensajes", json=payload, headers=headers).status_code == 200
        assert cliente.post("/api/v1/mensajes", json=payload, headers=headers).status_code == 200
        resp = cliente.post("/api/v1/mensajes", json=payload, headers=headers)
        assert resp.status_code == 429

    def test_dispositivos_distintos_no_comparten_cupo(self, cliente):
        """A diferencia del modelo de API key compartida, cada dispositivo
        tiene su propio cupo de rate limit."""
        headers_a, _ = _device_headers(cliente)
        headers_b, _ = _device_headers(cliente)
        session_a = cliente.post("/api/v1/sesiones", headers=headers_a).json()["session_id"]
        payload_a = {"mensaje": "hola", "session_id": session_a}

        cliente.post("/api/v1/mensajes", json=payload_a, headers=headers_a)
        cliente.post("/api/v1/mensajes", json=payload_a, headers=headers_a)
        # Dispositivo A ya agotó su cupo (2/min); B nunca lo usó.
        assert (
            cliente.post("/api/v1/mensajes", json=payload_a, headers=headers_a).status_code == 429
        )

        resp_b = cliente.post("/api/v1/sesiones", headers=headers_b)
        assert resp_b.status_code == 200


class TestPrivacidad:
    def test_aviso_privacidad_no_requiere_auth(self, cliente):
        resp = cliente.get("/privacidad")
        assert resp.status_code == 200
        assert "retencion_dias" in resp.json()
        assert "version" in resp.json()

    def test_documento_completo_apunta_a_una_ruta_servida_de_verdad(self, cliente):
        """El link que GET /privacidad anuncia como documento completo
        debe responder 200, no ser un enlace muerto."""
        ruta = cliente.get("/privacidad").json()["documento_completo"]
        resp = cliente.get(ruta)
        assert resp.status_code == 200
        assert "Aviso de privacidad" in resp.text

    def test_resumen_refleja_si_hay_cifrado_configurado(self, cliente):
        """El resumen no debe afirmar que el contenido se guarda cifrado
        cuando SANTISIMA_CLAVE_CIFRADO no está configurada."""
        resumen = cliente.get("/privacidad").json()["resumen"]
        assert "se cifran" in resumen

    def test_resumen_refleja_ausencia_de_cifrado_configurado(self, cliente, monkeypatch):
        """Sin SANTISIMA_CLAVE_CIFRADO (p. ej. en modo debug, donde
        validar_produccion no la exige) el resumen no debe afirmar que el
        contenido se guarda cifrado cuando no es cierto.

        ``delenv`` por sí solo no basta: solo quita la variable de
        ``os.environ``, pero pydantic-settings también lee ``.env`` como
        fuente — si el ``.env`` real de este checkout (el que se usa para
        correr la app de verdad) define una clave, esta prueba pasaría con
        él vacío mientras siguiera fallando en un dev local con `.env`
        completo, que es justo el entorno donde más importa que funcione.
        Fijar la variable a cadena vacía sí gana sobre `.env` sin importar
        qué haya ahí.
        """
        monkeypatch.setenv("SANTISIMA_CLAVE_CIFRADO", "")
        monkeypatch.setenv("SANTISIMA_DEBUG", "true")

        from la_santisima_conversacional import config as config_module

        config_module.get_settings.cache_clear()
        sys.modules.pop("la_santisima_conversacional.presentation.http_api", None)
        http_api = importlib.import_module("la_santisima_conversacional.presentation.http_api")

        with TestClient(http_api.app) as cliente_sin_cifrado:
            resumen = cliente_sin_cifrado.get("/privacidad").json()["resumen"]
            assert "SIN cifrar" in resumen

        config_module.get_settings.cache_clear()


class TestConsentimiento:
    """Consentimiento explícito diferenciado (ver docs/compliance/DPIA.md
    §4): un dispositivo no puede enviar un mensaje real hasta aceptar,
    explícitamente, la versión vigente del aviso de privacidad."""

    def test_registrar_dispositivo_no_exige_consentimiento(self, cliente):
        """El registro (y el saludo/consentimiento que lo acompaña en el
        cliente) no procesa contenido sensible — no debe bloquearse."""
        resp = cliente.post("/api/v1/dispositivos")
        assert resp.status_code == 200

    def test_mensaje_sin_consentimiento_devuelve_403(self, cliente):
        dispositivo = _registrar_dispositivo(cliente)
        headers = {"Authorization": f"Bearer {dispositivo['device_token']}"}
        session_id = cliente.post("/api/v1/sesiones", headers=headers).json()["session_id"]

        resp = cliente.post(
            "/api/v1/mensajes",
            json={"mensaje": "hola", "session_id": session_id},
            headers=headers,
        )
        assert resp.status_code == 403
        assert "consentimiento_requerido" in resp.json()["detail"]

    def test_mensaje_stream_sin_consentimiento_devuelve_403(self, cliente):
        dispositivo = _registrar_dispositivo(cliente)
        headers = {"Authorization": f"Bearer {dispositivo['device_token']}"}
        session_id = cliente.post("/api/v1/sesiones", headers=headers).json()["session_id"]

        resp = cliente.post(
            "/api/v1/mensajes/stream",
            json={"mensaje": "hola", "session_id": session_id},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_mensaje_stream_expone_emocion_en_evento_done(self, cliente):
        """La emoción detectada debe viajar en el evento SSE final ("done"),
        no mezclada con los chunks de texto plano (ver stub
        _responder_mensaje_stream, que retorna "devocion")."""
        headers, _ = _device_headers(cliente)
        session_id = cliente.post("/api/v1/sesiones", headers=headers).json()["session_id"]

        resp = cliente.post(
            "/api/v1/mensajes/stream",
            json={"mensaje": "hola La Santísima", "session_id": session_id},
            headers=headers,
        )
        assert resp.status_code == 200
        cuerpo = resp.text
        assert "data: Hola " in cuerpo
        assert "data: creyente." in cuerpo
        assert 'event: done\ndata: {"emocion": "devocion"}' in cuerpo

    def test_mensaje_tras_aceptar_consentimiento_funciona(self, cliente):
        dispositivo = _registrar_dispositivo(cliente)
        headers = {"Authorization": f"Bearer {dispositivo['device_token']}"}
        _aceptar_consentimiento(cliente, headers)
        session_id = cliente.post("/api/v1/sesiones", headers=headers).json()["session_id"]

        resp = cliente.post(
            "/api/v1/mensajes",
            json={"mensaje": "hola", "session_id": session_id},
            headers=headers,
        )
        assert resp.status_code == 200

    def test_aceptar_version_distinta_a_la_vigente_no_habilita_el_envio(self, cliente):
        """Aceptar una versión vieja (o cualquier otra que no sea la
        vigente) no debe contar como consentimiento válido — si el aviso
        cambió, hace falta re-aceptar la nueva."""
        dispositivo = _registrar_dispositivo(cliente)
        headers = {"Authorization": f"Bearer {dispositivo['device_token']}"}
        resp = cliente.post(
            "/api/v1/dispositivos/consentimiento",
            json={"version": "version-vieja-que-ya-no-es-la-vigente"},
            headers=headers,
        )
        assert resp.status_code == 204  # se registra lo que aceptó...

        session_id = cliente.post("/api/v1/sesiones", headers=headers).json()["session_id"]
        resp = cliente.post(
            "/api/v1/mensajes",
            json={"mensaje": "hola", "session_id": session_id},
            headers=headers,
        )
        assert resp.status_code == 403  # ...pero no habilita el envío.

    def test_consentimiento_requiere_device_token(self, cliente):
        resp = cliente.post("/api/v1/dispositivos/consentimiento", json={"version": "v1"})
        assert resp.status_code == 401


class TestCorsOrigenPropio:
    """Regresión del bug de arranque "Verifica tu conexión".

    El frontend servido por GET / llamaba a la API en
    ``http://127.0.0.1:8000`` fijo. Al abrir la app en
    ``http://localhost:8000`` (mismo backend, origen distinto para el
    navegador) toda llamada era cross-origin, y con
    ``SANTISIMA_CORS_ORIGINS`` apuntando solo a ``localhost:3000`` el
    preflight respondía 400 "Disallowed CORS origin". Un fallo de CORS se
    ve en el cliente igual que una caída de red, así que la UI mostraba
    "Verifica tu conexión" con el backend perfectamente sano.

    Estos tests fijan que el backend acepta su propio origen (y el
    equivalente loopback localhost/127.0.0.1) y sigue rechazando terceros.
    """

    def _preflight(self, cliente, origen: str, ruta: str = "/api/v1/dispositivos"):
        return cliente.options(
            ruta,
            headers={
                "Origin": origen,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    def test_preflight_desde_el_propio_origen_es_aceptado(self, cliente):
        """El caso exacto que fallaba: app servida por GET / en
        http://localhost:8000 llamando a la API en el mismo backend."""
        resp = self._preflight(cliente, "http://localhost:8000")
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == "http://localhost:8000"

    def test_loopback_localhost_y_127_son_equivalentes(self, cliente):
        """localhost y 127.0.0.1 son el mismo backend en loopback, pero el
        navegador los trata como orígenes distintos — deben autorizarse
        los dos, o abrir la app en uno y llamar al otro vuelve a romper
        el arranque."""
        for origen in (
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://localhost",
            "http://127.0.0.1:3000",
        ):
            resp = self._preflight(cliente, origen)
            assert resp.status_code == 200, origen
            assert resp.headers["access-control-allow-origin"] == origen

    def test_origen_de_terceros_sigue_rechazado(self, cliente):
        """El arreglo no debe abrir CORS a cualquiera: solo al propio
        origen de la app. Un host de red (o uno que solo *contiene* un
        loopback en el nombre) debe seguir recibiendo 400."""
        for origen in (
            "https://evil.example",
            "https://localhost.evil.example",
            "https://evil.example/127.0.0.1",
        ):
            resp = self._preflight(cliente, origen)
            assert resp.status_code == 400, origen
            assert "access-control-allow-origin" not in resp.headers, origen

    def test_health_es_alcanzable_por_el_propio_origen(self, cliente):
        """El sondeo de diagnóstico del frontend (fetch /health en modo
        no-cors) debe poder distinguir "backend caído" de "CORS": si el
        backend responde a GET /health, el arranque no falló por red."""
        resp = cliente.get("/health", headers={"Origin": "http://localhost:8000"})
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
