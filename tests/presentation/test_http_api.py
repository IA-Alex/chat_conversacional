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

    from src.la_santisima_conversacional import config as config_module

    config_module.get_settings.cache_clear()

    for nombre in ("src.la_santisima_conversacional.presentation.http_api",):
        sys.modules.pop(nombre, None)
    http_api = importlib.import_module("src.la_santisima_conversacional.presentation.http_api")

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

        from src.la_santisima_conversacional import config as config_module

        config_module.get_settings.cache_clear()
        import sys as _sys

        _sys.modules.pop("src.la_santisima_conversacional.presentation.http_api", None)
        http_api = importlib.import_module("src.la_santisima_conversacional.presentation.http_api")

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
        from src.la_santisima_conversacional.infrastructure.security import emitir_device_token
        from src.la_santisima_conversacional.config import Settings

        settings_ajenos = Settings(
            deepinfra_api_key="sk-test", session_secret="otro-secreto-totalmente-distinto"
        )
        token_ajeno = emitir_device_token("device-cualquiera", settings_ajenos)
        resp = cliente.post("/api/v1/sesiones", headers={"Authorization": f"Bearer {token_ajeno}"})
        assert resp.status_code == 401


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
        assert "Se guardan cifrados" in resumen

    def test_resumen_refleja_ausencia_de_cifrado_configurado(self, cliente, monkeypatch):
        """Sin SANTISIMA_CLAVE_CIFRADO (p. ej. en modo debug, donde
        validar_produccion no la exige) el resumen no debe afirmar que el
        contenido se guarda cifrado cuando no es cierto."""
        monkeypatch.delenv("SANTISIMA_CLAVE_CIFRADO", raising=False)
        monkeypatch.setenv("SANTISIMA_DEBUG", "true")

        from src.la_santisima_conversacional import config as config_module

        config_module.get_settings.cache_clear()
        sys.modules.pop("src.la_santisima_conversacional.presentation.http_api", None)
        http_api = importlib.import_module("src.la_santisima_conversacional.presentation.http_api")

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
